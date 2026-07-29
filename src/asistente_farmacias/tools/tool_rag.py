"""
tool_rag.py — Búsqueda semántica + re-rank + filter sobre el vademécum en Qdrant.

Mismo patrón que get_relevance_score() + filter_docs() en
Notebook_01_Ejercicio_Seguridad_Resultado.py:
  1. similarity_search trae K_RETRIEVAL candidatas por embeddings (recall alto,
     precisión no garantizada — un embedding puede traer algo "parecido" pero
     no realmente relevante).
  2. Un LLM puntúa cada candidata de 0 a 1 según relevancia real a la pregunta.
  3. Se descartan las que quedan bajo THRESHOLD, y se ordenan por score.
  4. Solo las que sobreviven se le muestran al agente principal para redactar
     la respuesta.

Por qué vale la pena el costo extra de un LLM call por búsqueda: con un
dataset de 220 fichas y embeddings de similitud coseno, es común que
lleguen 2-3 fichas "vecinas" que comparten vocabulario (ej. misma clase de
fármaco) pero no responden lo que se preguntó. El re-rank filtra ese ruido
antes de que llegue al agente — mejora precisión a cambio de más latencia
y costo por consulta (documentar este trade-off en el informe).

IMPORTANTE (guardrail): esta tool puede devolver el campo "Strength" (ej.
"325 mg") de la ficha — es un dato descriptivo, NO una recomendación de
dosis para una persona. Esa distinción la aplica el guardrail de salida
(guardrails/clinical_gate.py) sobre la respuesta final del agente, no esta
tool.
"""

import os

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from asistente_farmacias.resilience import invocar_con_fallback

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIMS = 256
COLLECTION = "vademecum_medicamentos"

K_RETRIEVAL = 8   # candidatas iniciales por similitud (antes del filtro)
THRESHOLD = 0.4   # descarta fichas con score de relevancia bajo esto
K_FINAL = 3        # máximo de fichas que se le muestran al agente, tras filtrar

_vector_store = None


def _get_vector_store() -> QdrantVectorStore:
    """Conexión perezosa a Qdrant — solo al primer uso real, no al arrancar
    el servidor (un fallo de Qdrant no debe tumbar toda la app al iniciar)."""
    global _vector_store
    if _vector_store is None:
        client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
        embeddings = OpenAIEmbeddings(model=EMBED_MODEL, dimensions=EMBED_DIMS)
        _vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION, embedding=embeddings)
    return _vector_store


def _puntuar_relevancia(pregunta: str, fichas: list, config: dict | None = None) -> list[float]:
    """Un LLM puntúa cada ficha recuperada, 0 a 1, según qué tan bien
    responde a la pregunta real — no solo si comparte vocabulario.
    Usa invocar_con_fallback: si el modelo principal falla (retirado,
    caído), prueba automáticamente el siguiente de la cadena.

    Usa texto plano (no with_structured_output) — ver la nota en
    clinical_gate.py sobre por qué with_structured_output combinado con
    contenido de medicamentos disparó falsos bloqueos de moderación."""
    prompt = """Evalúa qué tan relevante es esta ficha de medicamento para responder
la pregunta del usuario. Usa esta rúbrica:
- 0.0 Irrelevante: no tiene relación con lo preguntado.
- 0.25 Débil: comparte tema general pero no responde la pregunta específica.
- 0.5 Parcial: toca el tema pero le falta información clave.
- 0.75 Fuerte: responde la mayor parte de la pregunta.
- 1.0 Directa: responde exactamente lo preguntado.

Pregunta: {pregunta}

Ficha: {ficha}

Responde SOLO con el número (ej. "0.75"), nada más."""

    scores = []
    for ficha in fichas:
        resultado = invocar_con_fallback(
            prompt.format(pregunta=pregunta, ficha=ficha.page_content), config=config
        )
        try:
            score = float(resultado.content.strip().split()[0])
        except (ValueError, IndexError):
            score = 0.5  # valor neutro si no se pudo parsear
        scores.append(score)
    return scores


@tool
def buscar_ficha_medicamento(medicamento: str) -> str:
    """Busca información general de un medicamento en el vademécum (ficha técnica):
    clase, indicaciones, forma de dosificación de referencia, mecanismo de acción,
    efectos secundarios. Usa esta herramienta cuando el usuario pregunte qué es un
    medicamento, para qué sirve, o pida información general sobre él — NUNCA para
    decidir una dosis para una persona ni indicar tratamiento."""
    try:
        vector_store = _get_vector_store()
        candidatas = vector_store.similarity_search(medicamento, k=K_RETRIEVAL)
    except Exception as e:
        return f"No pude consultar el vademécum en este momento ({e!r})."

    if not candidatas:
        return f"No encontré información sobre '{medicamento}' en el vademécum indexado."

    try:
        scores = _puntuar_relevancia(medicamento, candidatas)
    except Exception:
        # Si el re-rank falla (ej. LLM caído), degradamos a las candidatas
        # crudas por similitud en vez de fallar toda la respuesta.
        scores = [1.0] * len(candidatas)

    puntuadas = list(zip(candidatas, scores))
    puntuadas.sort(key=lambda par: par[1], reverse=True)
    filtradas = [(ficha, score) for ficha, score in puntuadas if score >= THRESHOLD][:K_FINAL]

    if not filtradas:
        return (
            f"Encontré resultados parecidos a '{medicamento}' pero ninguno lo "
            f"suficientemente relevante en el vademécum indexado."
        )

    bloques = []
    for ficha, score in filtradas:
        bloques.append(
            f"[Fuente: {ficha.metadata.get('fuente', 'vademécum')} — "
            f"{ficha.metadata.get('drug_name', '?')} · relevancia={score:.2f}]\n"
            f"{ficha.page_content}"
        )
    return "\n\n".join(bloques)