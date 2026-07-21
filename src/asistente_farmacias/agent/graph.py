"""
graph.py — Agente LangGraph (stage 0 · esqueleto).

Usa `create_react_agent` (prebuilt de LangGraph) con dos tools STUB y un
`MemorySaver` como checkpointer. El checkpointer es lo que da estado: cada
`user_id` se mapea a un `thread_id` distinto, así que el historial de cada
persona queda separado y persiste entre turnos (mientras el proceso viva —
en stage 0 la memoria es en RAM, se pierde si el servidor se reinicia).

Por qué create_react_agent y no un StateGraph 100% manual, por ahora:
  - Ya resuelve el routing entre tools (el LLM decide cuál llamar según la
    pregunta) y la integración con el checkpointer, con muy poco código —
    ideal para validar la tubería completa rápido.
  - Sigue siendo LangGraph "de verdad" por debajo (compila a un StateGraph).
  - Cuando lleguemos a la rama feature/guardrails, vamos a evaluar si
    conviene envolver esto en un grafo manual con nodos explícitos de
    guardrail de entrada/salida (más control, más código) — decisión para
    discutir con calma en ese momento, no ahora.

TODO (ramas siguientes):
  - Reemplazar tools stub por las reales (MINSAL, RAG).
  - Evaluar checkpointer persistente (no en RAM) antes del deploy final.
  - Sumar nodos explícitos de guardrail si create_react_agent no alcanza.
"""

import os

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from asistente_farmacias.tools.tool_minsal import (
    consultar_farmacias_de_turno,
    consultar_farmacias_registradas,
)
from asistente_farmacias.tools.tool_rag import buscar_ficha_medicamento
from asistente_farmacias.guardrails.basic import SYSTEM_PROMPT_GUARDRAIL

# gpt-4o-mini está en retiro. El modelo vigente equivalente es
# gpt-5.4-mini (la misma familia que ya usaste en la tarea de conducción).

GEN_MODEL = os.getenv("GEN_MODEL", "gpt-5.4-mini")

SYSTEM_PROMPT = (
    "Eres un asistente informativo sobre farmacias de turno y medicamentos "
    "en Chile. Usa 'consultar_farmacias_de_turno' cuando pregunten qué "
    "farmacia está ABIERTA/DE TURNO ahora mismo. Usa "
    "'consultar_farmacias_registradas' cuando pregunten si existe una "
    "farmacia en particular o quieran un listado general (sin importar si "
    "está abierta ahora). Usa 'buscar_ficha_medicamento' para preguntas "
    "sobre qué es un medicamento o para qué sirve. "
    "No inventes información que las herramientas no te dieron. "
    + SYSTEM_PROMPT_GUARDRAIL
)

# El checkpointer vive en memoria del proceso en este stage — se reemplaza
# por uno persistente antes de desplegar en serio.
_checkpointer = MemorySaver()

_agent = create_react_agent(
    model=ChatOpenAI(model=GEN_MODEL, temperature=0),
    tools=[consultar_farmacias_de_turno, consultar_farmacias_registradas, buscar_ficha_medicamento],
    prompt=SYSTEM_PROMPT,
    checkpointer=_checkpointer,
)


def responder(user_id: str, pregunta: str) -> str:
    """Invoca el agente en el 'hilo' de conversación de este user_id.

    thread_id = user_id es lo que le da memoria por usuario: LangGraph
    guarda el historial de mensajes asociado a ese thread_id y se lo
    reinyecta automáticamente en cada llamada nueva.
    """
    config = {"configurable": {"thread_id": user_id}}
    resultado = _agent.invoke(
        {"messages": [{"role": "user", "content": pregunta}]}, config=config
    )
    return resultado["messages"][-1].content
