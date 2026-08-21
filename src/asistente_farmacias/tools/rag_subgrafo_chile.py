"""
rag_subgrafo_chile.py — Sub-grafo del RAG para el vademécum CHILENO (JSON
del profesor), independiente del vademécum de Kaggle (rag_subgrafo.py).
Mismo patrón exacto: retrieve → rerank → filter como nodos explícitos —
ver rag_subgrafo.py para el razonamiento completo de por qué es un
sub-grafo separado del grafo principal, y por qué config va como parámetro
del nodo (LangGraph lo inyecta) en vez de vivir en el estado.

Por qué un archivo aparte, y no reutilizar rag_subgrafo.py con un parámetro
de colección: cada vademécum tiene su propio umbral de similitud mínima,
calibrado con evidencia real y propia de SU corpus — mezclar ambos en un
solo archivo parametrizado complica innecesariamente algo que hoy es
simple, y separa con claridad qué pertenece a cada fuente de datos.

Hallazgo real que motivó recalibrar el umbral (no reusar el 0.4 de Kaggle):
con muestras de 50 y luego 500 medicamentos indexados, la pregunta
"Aartfenacin" (antihistamínico, Fexofenadina) devolvía consistentemente
"ABATERO" (Abiraterona, oncológico — sin relación real) como candidata con
score ~0.517 — más alto que el umbral de Kaggle (0.4), así que ese umbral
habría dejado pasar el falso positivo. El mismo caso se repitió con 50 y
con 500 medicamentos (no era ruido de muestra chica), señal de que este
corpus necesita un umbral más exigente. Se calibró en 0.55: por encima del
falso positivo confirmado (0.517), por debajo de los casos genuinamente
relevantes observados (Aartfenacin 0.549-0.606 según la pregunta, Aartiflox
0.655, Acecnou/Fosfomicina 0.601 para una pregunta de infección urinaria).
Pendiente: re-confirmar este umbral una vez indexado el dataset completo
(12,411 fichas) — con más candidatas reales disponibles, la distribución de
scores puede desplazarse.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langgraph.graph import END, START, StateGraph
from qdrant_client import QdrantClient

from asistente_farmacias.resilience import invocar_con_fallback

_PROMPT_VERIFICAR_MEDICAMENTO = """Un usuario preguntó por un medicamento. Un
sistema de búsqueda encontró una ficha con el nombre que se muestra abajo.
Considerando que la pregunta puede venir en otro idioma, con errores de
tipeo, abreviada, o usando el nombre comercial en vez del genérico (o
viceversa): ¿es razonable que la ficha encontrada sea sobre EL MISMO
medicamento que preguntó la persona, o uno directamente relacionado
(ej. mismo principio activo)?

Pregunta del usuario: {pregunta}
Nombre de la ficha encontrada: {nombre_ficha}

Responde SOLO "si" o "no", nada más."""


def _es_medicamento_relacionado(pregunta: str, nombre_ficha: str, config: RunnableConfig) -> bool:
    """Verificación con LLM, no con comparación de texto (prefijos,
    substrings) — un LLM entiende traducciones, typos y abreviaciones mucho
    mejor que cualquier regla de texto rígida (ej. "paractml" -> Paracetamol,
    "Aartfenacin" -> nada relacionado con "Allopurinol"). Si falla la
    llamada, se asume relacionado (fail-open acá: es preferible mostrar un
    resultado dudoso que bloquear uno bueno por un error técnico de esta
    verificación, ya que el LLM que arma la respuesta final igual puede
    detectar y aclarar un desajuste, como ya se confirmó con evidencia real)."""
    try:
        resultado = invocar_con_fallback(
            _PROMPT_VERIFICAR_MEDICAMENTO.format(pregunta=pregunta, nombre_ficha=nombre_ficha),
            config=config,
        )
        return resultado.content.strip().lower().startswith("si")
    except Exception:
        return True

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIMS = 256
COLLECTION = "vademecum_chile"

K_RETRIEVAL = 8
K_FINAL = 3

# Ver docstring del módulo: calibrado con evidencia real (falso positivo
# Aartfenacin/Abatero a 0.517), NO reutiliza el 0.4 de rag_subgrafo.py.
# Confirmado con dos corridas (50 y 500 medicamentos): 0.54 descarta el
# falso positivo (0.517) sin perder la segunda presentación real de
# Aartfenacin (0.549, justo en el filo si el umbral fuera 0.55).
EMBEDDING_THRESHOLD_MINIMO = 0.54
THRESHOLD = 0.54

# Mismo criterio de decisión que rag_subgrafo.py: desactivado por defecto,
# disponible como flag. Con este corpus (12,411 fichas, bastante más grande
# y potencialmente más ambiguo que las 220 de Kaggle) vale la pena revisar
# esta decisión con un mini-eval propio antes de la entrega, en vez de
# asumir que el mismo resultado de Kaggle aplica igual acá.
RERANK_ACTIVADO = os.getenv("RERANK_ACTIVADO_CHILE", "false").lower() == "true"

_RERANK_PROMPT = """Evalúa qué tan relevante es esta ficha de medicamento para responder
la pregunta del usuario. Usa esta rúbrica:
- 0.0 Irrelevante: no tiene relación con lo preguntado.
- 0.25 Débil: comparte tema general pero no responde la pregunta específica.
- 0.5 Parcial: toca el tema pero le falta información clave.
- 0.75 Fuerte: responde la mayor parte de la pregunta.
- 1.0 Directa: responde exactamente lo preguntado.

Pregunta: {pregunta}

Ficha: {ficha}

Responde SOLO con el número (ej. "0.75"), nada más."""

_vector_store = None


def _get_vector_store() -> QdrantVectorStore:
    global _vector_store
    if _vector_store is None:
        client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
        embeddings = OpenAIEmbeddings(model=EMBED_MODEL, dimensions=EMBED_DIMS)
        _vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION, embedding=embeddings)
    return _vector_store


class RagStateChile(TypedDict, total=False):
    pregunta: str
    candidatas: list
    scores_embedding: list[float]
    puntuadas: list  # [(ficha, score), ...]
    filtradas: list  # [(ficha, score), ...] — el resultado final


def nodo_retrieve(estado: RagStateChile) -> RagStateChile:
    vector_store = _get_vector_store()
    resultados = vector_store.similarity_search_with_score(estado["pregunta"], k=K_RETRIEVAL)
    candidatas = [doc for doc, score in resultados]
    scores_embedding = [score for doc, score in resultados]
    print(f"🔍 retrieve (chile) · scores de embeddings: {[round(s, 3) for s in scores_embedding]}")
    return {"candidatas": candidatas, "scores_embedding": scores_embedding}


def nodo_rerank(estado: RagStateChile, config: RunnableConfig) -> RagStateChile:
    candidatas = estado["candidatas"]
    scores_embedding = estado["scores_embedding"]

    candidatas_filtradas = []
    scores_filtrados = []
    for ficha, score in zip(candidatas, scores_embedding):
        if score >= EMBEDDING_THRESHOLD_MINIMO:
            candidatas_filtradas.append(ficha)
            scores_filtrados.append(score)

    if not candidatas_filtradas:
        print("🔍 filtro de embeddings (chile) · ninguna candidata superó el umbral mínimo (LLM rerank NO se llamó)")
        return {"puntuadas": []}

    # Verificación adicional: ¿la MEJOR candidata (mayor score) tiene
    # relación real con lo preguntado? Ver docstring del módulo y el mismo
    # bloque en rag_subgrafo.py (Kaggle) para el hallazgo completo que
    # motivó esto. Si la mejor no sirve, las demás (score aún más bajo)
    # tampoco — se descartan todas.
    mejor_ficha = candidatas_filtradas[0]
    nombre_mejor = mejor_ficha.metadata.get("nombre", mejor_ficha.page_content[:50])
    if not _es_medicamento_relacionado(estado["pregunta"], nombre_mejor, config):
        print(f"🔍 verificación LLM (chile) · '{nombre_mejor}' no está relacionado con la pregunta — se descarta todo")
        return {"puntuadas": []}

    if not RERANK_ACTIVADO:
        return {"puntuadas": list(zip(candidatas_filtradas, scores_filtrados))}

    def _puntuar_una(ficha) -> float:
        try:
            resultado = invocar_con_fallback(
                _RERANK_PROMPT.format(pregunta=estado["pregunta"], ficha=ficha.page_content),
                config=config,
            )
            return float(resultado.content.strip().split()[0])
        except (ValueError, IndexError, RuntimeError):
            return 0.5

    with ThreadPoolExecutor(max_workers=max(len(candidatas_filtradas), 1)) as executor:
        scores = list(executor.map(_puntuar_una, candidatas_filtradas))

    return {"puntuadas": list(zip(candidatas_filtradas, scores))}


def nodo_filter(estado: RagStateChile) -> RagStateChile:
    ordenadas = sorted(estado["puntuadas"], key=lambda par: par[1], reverse=True)
    filtradas = [(ficha, score) for ficha, score in ordenadas if score >= THRESHOLD][:K_FINAL]
    return {"filtradas": filtradas}


def _construir_subgrafo():
    grafo = StateGraph(RagStateChile)
    grafo.add_node("retrieve", nodo_retrieve)
    grafo.add_node("rerank", nodo_rerank)
    grafo.add_node("filter", nodo_filter)
    grafo.add_edge(START, "retrieve")
    grafo.add_edge("retrieve", "rerank")
    grafo.add_edge("rerank", "filter")
    grafo.add_edge("filter", END)
    return grafo.compile()


_subgrafo = _construir_subgrafo()


def invocar_subgrafo_chile(pregunta: str, config: RunnableConfig | None = None) -> list:
    """Punto de entrada equivalente a invocar_subgrafo() de rag_subgrafo.py,
    pero contra la colección vademecum_chile. Devuelve [(ficha, score), ...]
    ya filtradas y ordenadas."""
    resultado = _subgrafo.invoke({"pregunta": pregunta}, config=config)
    return resultado["filtradas"]