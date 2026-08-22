"""
rag_subgrafo.py — Sub-grafo del RAG: retrieve → rerank → filter como nodos
explícitos, en vez de vivir "escondidos" dentro de una sola función de tool.

Por qué un SUB-grafo, y no meter estos 3 pasos en el grafo PRINCIPAL
(agent/graph.py): el grafo principal tiene que elegir entre 3 herramientas
(2 de MINSAL + esta de RAG) — retrieve/rerank/filter solo tienen sentido
cuando la pregunta es de medicamentos, no cuando es de farmacias.

Historial de fixes reales encontrados durante el desarrollo:
1. TypeError de serialización: el config de observabilidad NO puede vivir
   en el estado del grafo (rompe con CallbackManager no serializable) —
   se pasa como parámetro del nodo, LangGraph lo inyecta solo.
2. Re-rank paralelizado (ThreadPoolExecutor): de ~8x el tiempo de una
   llamada a ~1x, sin cambiar el costo en tokens.
3. RERANK_ACTIVADO=false por defecto: el mini-eval no mostró mejora de
   calidad medible con este corpus (220 fichas atómicas).
4. Filtro de similitud mínima de embeddings (este cambio): sin re-rank
   LLM, TODAS las candidatas recibían score=1.0 sin ninguna discriminación
   real — cuando el medicamento preguntado NO existe en el corpus (ej.
   "Viadil", marca chilena ausente del dataset internacional), el sistema
   igual devolvía el "menos malo" de los candidatos como si fuera la
   respuesta correcta (ej. entregó info de Venlafaxina para una pregunta
   sobre Viadil). Este filtro usa el score REAL de similitud de coseno de
   Qdrant (gratis, sin LLM) para descartar candidatas que ni remotamente
   se parecen a la pregunta, incluso con el re-rank LLM apagado.
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
COLLECTION = "vademecum_medicamentos"

K_RETRIEVAL = 8
THRESHOLD = 0.4
K_FINAL = 1  # antes 3: con 3 fichas, el agente citaba fuentes que no
             # terminaba usando en el texto de la respuesta (ej. preguntar
             # por Ibuprofeno y citar también Paracetamol, sin mencionarlo)
             # — con 1 sola ficha, la cita siempre coincide con lo dicho.

# EMBEDDING_THRESHOLD_MINIMO: valor de partida razonable, NO calibrado aún
# con datos reales de tu corpus. El código imprime el score real de cada
# consulta en la terminal — ajusta este número después de ver varios casos
# reales (uno donde SÍ está el medicamento, uno donde NO, como Viadil).
# se probó el 0.35 sirve, pero cuando colocamos medicamento + sintoma
# se cae, probar 0.5, se cambia a 0.4 porque pregunta como para que 
#sirve el ibuprofeno que si esta en la data lo excluye
EMBEDDING_THRESHOLD_MINIMO = 0.4

# Re-rank del RAG: DESACTIVADO por defecto. Justificación (medida, no
# asumida): el mini-eval (eval_vademecum.py) comparó sin_rerank vs
# con_rerank sobre 3 preguntas de vademécum — AMBAS versiones obtuvieron
# 1.00 en correctness/faithfulness/relevance, sin diferencia de calidad
# medible. Con un corpus chico y muy estructurado (220 fichas atómicas) y
# preguntas dominadas por el nombre del medicamento (señal casi inequívoca
# para el embedding), el retrieval simple ya acierta sin necesitar una
# segunda pasada de puntuación LLM. Se mantiene como flag disponible si el
# corpus crece o se vuelve más ambiguo.
RERANK_ACTIVADO = os.getenv("RERANK_ACTIVADO", "false").lower() == "true"

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


class RagState(TypedDict, total=False):
    pregunta: str
    candidatas: list
    scores_embedding: list[float]
    puntuadas: list  # [(ficha, score), ...]
    filtradas: list  # [(ficha, score), ...] — el resultado final


def nodo_retrieve(estado: RagState) -> RagState:
    vector_store = _get_vector_store()
    resultados = vector_store.similarity_search_with_score(estado["pregunta"], k=K_RETRIEVAL)
    candidatas = [doc for doc, score in resultados]
    scores_embedding = [score for doc, score in resultados]
    print(f"🔍 retrieve · scores de embeddings: {[round(s, 3) for s in scores_embedding]}")
    return {"candidatas": candidatas, "scores_embedding": scores_embedding}


def nodo_rerank(estado: RagState, config: RunnableConfig) -> RagState:
    """`config` como segundo parámetro: LangGraph lo inyecta automáticamente
    en tiempo de ejecución — NO vive en el estado, así que no rompe la
    serialización.

    Primero aplica el filtro de similitud mínima de embeddings (siempre
    activo, gratis, sin LLM). Recién después, si RERANK_ACTIVADO=true,
    hace el re-rank LLM en paralelo sobre lo que sobrevivió ese filtro.

    Hallazgo real (agosto 2026): al agregar el vademécum chileno como
    fallback, se detectó que el umbral de similitud (0.4) deja pasar
    candidatas SIN relación real cuando el medicamento preguntado no existe
    en absoluto en este corpus (ej. "Aartfenacin" -> traía "Allopurinol",
    score 0.508, sin relación real). El umbral nunca fue diseñado para
    distinguir "no hay nada aquí" de "esto es lo más parecido que hay" —
    solo para no descartar candidatas que sí existían. Se agregó una
    verificación adicional con LLM (más robusta que comparar texto: entiende
    traducciones, typos, abreviaciones) SOLO sobre la mejor candidata, antes
    de aceptar el resultado del filtro de embeddings como válido."""
    candidatas = estado["candidatas"]
    scores_embedding = estado["scores_embedding"]

    candidatas_filtradas = []
    scores_filtrados = []
    for ficha, score in zip(candidatas, scores_embedding):
        if score >= EMBEDDING_THRESHOLD_MINIMO:
            candidatas_filtradas.append(ficha)
            scores_filtrados.append(score)

    if not candidatas_filtradas:
        print("🔍 filtro de embeddings · ninguna candidata superó el umbral mínimo (LLM rerank NO se llamó)")
        return {"puntuadas": []}

    # Verificación adicional: ¿la MEJOR candidata (la de mayor score) tiene
    # relación real con lo preguntado? Si no, se descartan todas — si la
    # mejor no sirve, las demás (con score aún más bajo) tampoco.
    mejor_ficha = candidatas_filtradas[0]
    nombre_mejor = mejor_ficha.metadata.get("drug_name", mejor_ficha.page_content[:50])
    if not _es_medicamento_relacionado(estado["pregunta"], nombre_mejor, config):
        print(f"🔍 verificación LLM · '{nombre_mejor}' no está relacionado con la pregunta — se descarta todo")
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


def nodo_filter(estado: RagState) -> RagState:
    ordenadas = sorted(estado["puntuadas"], key=lambda par: par[1], reverse=True)
    filtradas = [(ficha, score) for ficha, score in ordenadas if score >= THRESHOLD][:K_FINAL]
    return {"filtradas": filtradas}


def _construir_subgrafo():
    grafo = StateGraph(RagState)
    grafo.add_node("retrieve", nodo_retrieve)
    grafo.add_node("rerank", nodo_rerank)
    grafo.add_node("filter", nodo_filter)
    grafo.add_edge(START, "retrieve")
    grafo.add_edge("retrieve", "rerank")
    grafo.add_edge("rerank", "filter")
    grafo.add_edge("filter", END)
    return grafo.compile()


_subgrafo = _construir_subgrafo()


def invocar_subgrafo(pregunta: str, config: RunnableConfig | None = None) -> list:
    """Punto de entrada que usa tool_rag.py. Devuelve [(ficha, score), ...]
    ya filtradas y ordenadas."""
    resultado = _subgrafo.invoke({"pregunta": pregunta}, config=config)
    return resultado["filtradas"]