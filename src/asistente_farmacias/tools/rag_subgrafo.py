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
mismo callback de Langfuse, igual queda visible y anidado en la traza.

Experimento en rama feature/rag-nodos-explicitos: comparar cómo se ve esto
en Langfuse contra la versión anterior (todo en una sola función), antes
de decidir si vale la pena el cambio.
"""

import os
from typing import TypedDict

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


def nodo_rerank(estado: RagState) -> RagState:
    config = estado.get("_config")  # ver nota en invocar_subgrafo() más abajo
    puntuadas = []
    for ficha in estado["candidatas"]:
        try:
            resultado = invocar_con_fallback(
                _RERANK_PROMPT.format(pregunta=estado["pregunta"], ficha=ficha.page_content),
                config=config,
            )
            score = float(resultado.content.strip().split()[0])
        except (ValueError, IndexError, RuntimeError):
            score = 0.5  # valor neutro si falla el parseo o todos los modelos fallan
        puntuadas.append((ficha, score))
    return {"puntuadas": puntuadas}


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


def invocar_subgrafo(pregunta: str, config: dict | None = None) -> list:
    """Punto de entrada que usa tool_rag.py. Devuelve [(ficha, score), ...]
    ya filtradas y ordenadas.

    Nota sobre el config: se lo pasamos al invoke() del sub-grafo (para que
    LangGraph propague el callback de Langfuse a los nodos), y ADEMÁS lo
    guardamos dentro del estado (_config) para que nodo_rerank pueda
    reenviarlo a invocar_con_fallback — LangGraph no propaga automáticamente
    el config a llamadas manuales de LLM hechas DENTRO de un nodo, solo a
    los Runnables que se invocan con ese mismo config explícito.
    """
    estado_inicial = {"pregunta": pregunta, "_config": config}
    resultado = _subgrafo.invoke(estado_inicial, config=config)
    return resultado["filtradas"]