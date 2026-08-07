"""
rag_subgrafo.py — Sub-grafo del RAG: retrieve → rerank → filter como nodos
explícitos, en vez de vivir "escondidos" dentro de una sola función de tool.

Por qué un SUB-grafo, y no meter estos 3 pasos en el grafo PRINCIPAL
(agent/graph.py): el grafo principal tiene que elegir entre 3 herramientas
(2 de MINSAL + esta de RAG) — retrieve/rerank/filter solo tienen sentido
cuando la pregunta es de medicamentos, no cuando es de farmacias. Ponerlos
como nodos del grafo principal forzaría ese camino fijo para TODAS las
preguntas. Como sub-grafo invocado solo por la tool de RAG, se ejecuta
únicamente cuando el agente decide llamar a esa tool — y si le pasamos el
mismo callback de Langfuse/LangSmith, igual queda visible y anidado en la
traza.

BUG encontrado y corregido: la primera versión guardaba el `config` (con
los callbacks de observabilidad) DENTRO del estado del grafo, para que
nodo_rerank pudiera reenviarlo. Eso rompía todo con
`TypeError: Type is not msgpack serializable: CallbackManager` — LangGraph
necesita poder serializar el estado (para trazas/checkpoints), y un
CallbackManager no es serializable. La forma correcta: declarar `config`
como SEGUNDO PARÁMETRO de la función del nodo — LangGraph lo inyecta solo,
en tiempo de ejecución, sin que tenga que pasar por el estado.

Experimento en rama feature/rag-nodos-explicitos: comparar cómo se ve esto
en Langfuse/LangSmith contra la versión anterior (todo en una sola
función), antes de decidir si vale la pena el cambio.
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

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIMS = 256
COLLECTION = "vademecum_medicamentos"

K_RETRIEVAL = 8
THRESHOLD = 0.4
K_FINAL = 3

# --- Flag: re-rank activado/desactivado -------------------------------------
# DESACTIVADO por defecto. Justificación (medida, no asumida):
#   El mini-eval (eval_vademecum.py) comparó sin_rerank vs con_rerank sobre
#   3 preguntas de vademécum: AMBAS versiones obtuvieron 1.00 en
#   correctness/faithfulness/relevance — sin diferencia de calidad medible.
#   Con un corpus chico y muy estructurado (220 fichas atómicas, 1
#   medicamento = 1 unidad clara) y preguntas dominadas por el nombre del
#   medicamento (señal casi inequívoca para el embedding), el retrieval
#   simple ya acierta sin necesitar una segunda pasada de puntuación LLM.
#   El re-rank sí puede justificarse en el futuro si el corpus crece mucho,
#   se vuelve más ambiguo/solapado, o las preguntas dejan de nombrar el
#   medicamento directamente — por eso queda como flag, no eliminado.
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
    puntuadas: list  # [(ficha, score), ...]
    filtradas: list  # [(ficha, score), ...] — el resultado final


def nodo_retrieve(estado: RagState) -> RagState:
    vector_store = _get_vector_store()
    candidatas = vector_store.similarity_search(estado["pregunta"], k=K_RETRIEVAL)
    return {"candidatas": candidatas}


def nodo_rerank(estado: RagState, config: RunnableConfig) -> RagState:
    """`config` como segundo parámetro: LangGraph lo inyecta automáticamente
    en tiempo de ejecución (viene del invoke() de más abajo) — NO vive en
    el estado, así que no rompe la serialización.

    Si RERANK_ACTIVADO es False (default), este nodo NO llama al LLM —
    le asigna score=1.0 a todas las candidatas, preservando el orden que ya
    trae similarity_search (retrieval simple, degradación intencional, ver
    justificación junto a RERANK_ACTIVADO más arriba).

    Cuando SÍ está activado, las llamadas al LLM corren EN PARALELO
    (ThreadPoolExecutor), no en secuencia — con 8 candidatas, esto reduce
    la latencia de ~8x el tiempo de una llamada a ~1x."""

    candidatas = estado["candidatas"]

    if not RERANK_ACTIVADO:
        return {"puntuadas": [(ficha, 1.0) for ficha in candidatas]}

    def _puntuar_una(ficha) -> float:
        try:
            resultado = invocar_con_fallback(
                _RERANK_PROMPT.format(pregunta=estado["pregunta"], ficha=ficha.page_content),
                config=config,
            )
            return float(resultado.content.strip().split()[0])
        except (ValueError, IndexError, RuntimeError):
            return 0.5  # valor neutro si falla el parseo o todos los modelos fallan

    with ThreadPoolExecutor(max_workers=max(len(candidatas), 1)) as executor:
        scores = list(executor.map(_puntuar_una, candidatas))

    return {"puntuadas": list(zip(candidatas, scores))}


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
    ya filtradas y ordenadas.

    El config se pasa SOLO como parámetro de invoke() — LangGraph lo
    propaga a cada nodo automáticamente (incluido nodo_rerank, que lo
    recibe como segundo argumento). No se guarda en el estado inicial."""
    resultado = _subgrafo.invoke({"pregunta": pregunta}, config=config)
    return resultado["filtradas"]