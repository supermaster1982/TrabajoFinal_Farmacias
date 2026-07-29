"""
graph.py — StateGraph explícito con guardas de seguridad clínica.

Arquitectura (mismo patrón que Notebook_01_Ejercicio_Seguridad_Resultado.py
de la clase, adaptado de "guarda de tópico" a "guarda clínica"):

    START → gate_entrada (¿pide dosis/tratamiento?)
               ├── SÍ → nodo_respuesta_segura → END
               └── NO → nodo_agente (create_react_agent + memoria, ya validado)
                            → gate_salida (¿la respuesta igual recomendó algo?)
                                 ├── SÍ → nodo_respuesta_segura → END
                                 └── NO → END (respuesta tal cual)

El agente ReAct (con las 3 tools + MemorySaver por user_id) que ya
validamos en stage 0 queda INTACTO — vive como un nodo adentro de este
grafo más grande, no se reescribió su lógica interna.

Por qué dos guardas (entrada y salida) y no solo una: ver docstring de
`guardrails/clinical_gate.py`.
"""

import os
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from asistente_farmacias.tools.tool_minsal import (
    consultar_farmacias_de_turno,
    consultar_farmacias_registradas,
)
from asistente_farmacias.tools.tool_rag import buscar_ficha_medicamento
from asistente_farmacias.guardrails.clinical_gate import (
    MENSAJE_SEGURO,
    evaluar_entrada,
    evaluar_salida,
)

# --- Observabilidad con Langfuse Cloud (opcional y degradante) --------------
_LANGFUSE_ACTIVO = bool(os.getenv("LANGFUSE_PUBLIC_KEY")) and bool(os.getenv("LANGFUSE_SECRET_KEY"))
_langfuse_handler = None
_langfuse_client = None

if _LANGFUSE_ACTIVO:
    try:
        from langfuse import get_client
        from langfuse.langchain import CallbackHandler

        _langfuse_client = get_client()
        if _langfuse_client.auth_check():
            _langfuse_handler = CallbackHandler()
            print(f"✅ Langfuse activo → {os.getenv('LANGFUSE_BASE_URL')}")
        else:
            print("⚠️  Las claves de Langfuse no pasaron auth_check() — continuando sin trazas.")
    except Exception as e:
        print(f"⚠️  No se pudo inicializar Langfuse: {e!r} — continuando sin trazas.")
else:
    print("ℹ️  Sin claves de Langfuse en .env — continuando sin trazas.")

GEN_MODEL = os.getenv("GEN_MODEL", "gpt-5.4-mini")

SYSTEM_PROMPT = (
    "Eres un asistente informativo sobre farmacias de turno y medicamentos "
    "en Chile. Usa 'consultar_farmacias_de_turno' cuando pregunten qué "
    "farmacia está ABIERTA/DE TURNO ahora mismo. Usa "
    "'consultar_farmacias_registradas' cuando pregunten si existe una "
    "farmacia en particular o quieran un listado general (sin importar si "
    "está abierta ahora). Usa 'buscar_ficha_medicamento' para preguntas "
    "sobre qué es un medicamento o para qué sirve. "
    "Si 'consultar_farmacias_de_turno' no encuentra resultados para una "
    "comuna, intenta también 'consultar_farmacias_registradas' para esa "
    "misma comuna y ofrece esa información como alternativa, dejando claro "
    "que esas farmacias pueden no estar abiertas ahora mismo. "
    "No inventes información que las herramientas no te dieron. Nunca "
    "recomiendas medicamentos, dosis, ni tratamientos."
)

_checkpointer = MemorySaver()

_react_agent = create_react_agent(
    model=ChatOpenAI(model=GEN_MODEL, temperature=0),
    tools=[consultar_farmacias_de_turno, consultar_farmacias_registradas, buscar_ficha_medicamento],
    prompt=SYSTEM_PROMPT,
    checkpointer=_checkpointer,
)


class EstadoConversacion(TypedDict, total=False):
    user_id: str
    pregunta: str
    bloqueado_en_entrada: bool
    razon_entrada: str
    respuesta_agente: str
    bloqueado_en_salida: bool
    razon_salida: str
    respuesta_final: str


def _lf_config() -> dict:
    """Config de Langfuse a reutilizar en cada nodo que llama a un LLM
    (guarda de entrada, agente, guarda de salida) — así TODAS las llamadas
    quedan trazadas, no solo la del agente. Esto importa especialmente para
    los casos BLOQUEADOS: si el guardrail nunca traza su propia decisión,
    la demo no puede mostrar evidencia de que el bloqueo realmente ocurrió."""
    return {"callbacks": [_langfuse_handler]} if _langfuse_handler else {}


def _nodo_gate_entrada(estado: EstadoConversacion) -> EstadoConversacion:
    try:
        evaluacion = evaluar_entrada(estado["pregunta"], config=_lf_config())
        return {"bloqueado_en_entrada": evaluacion.es_peligroso, "razon_entrada": evaluacion.razon}
    except Exception as e:
        # Fail-closed: si la guarda misma falla (ej. el filtro de moderación
        # del proveedor del LLM bloqueó la llamada porque la pregunta era
        # demasiado explícita), tratamos esto como "peligroso" por defecto.
        # Un control de seguridad que no puede evaluar debe negar, no dejar
        # pasar — documentar este caso en el informe/matriz de riesgos.
        return {"bloqueado_en_entrada": True, "razon_entrada": f"Guarda de entrada falló ({e!r}); fail-closed."}


def _nodo_agente(estado: EstadoConversacion) -> EstadoConversacion:
    config = {"configurable": {"thread_id": estado["user_id"]}, **_lf_config()}
    resultado = _react_agent.invoke(
        {"messages": [{"role": "user", "content": estado["pregunta"]}]}, config=config
    )
    return {"respuesta_agente": resultado["messages"][-1].content}


def _nodo_gate_salida(estado: EstadoConversacion) -> EstadoConversacion:
    try:
        evaluacion = evaluar_salida(estado["respuesta_agente"], config=_lf_config())
        return {"bloqueado_en_salida": evaluacion.es_peligroso, "razon_salida": evaluacion.razon}
    except Exception as e:
        return {"bloqueado_en_salida": True, "razon_salida": f"Guarda de salida falló ({e!r}); fail-closed."}


def _nodo_respuesta_segura(estado: EstadoConversacion) -> EstadoConversacion:
    return {"respuesta_final": MENSAJE_SEGURO}


def _nodo_respuesta_ok(estado: EstadoConversacion) -> EstadoConversacion:
    return {"respuesta_final": estado["respuesta_agente"]}


def _routing_entrada(estado: EstadoConversacion) -> str:
    return "bloqueado" if estado.get("bloqueado_en_entrada") else "permitido"


def _routing_salida(estado: EstadoConversacion) -> str:
    return "bloqueado" if estado.get("bloqueado_en_salida") else "permitido"


def _construir_grafo():
    grafo = StateGraph(EstadoConversacion)
    grafo.add_node("gate_entrada", _nodo_gate_entrada)
    grafo.add_node("agente", _nodo_agente)
    grafo.add_node("gate_salida", _nodo_gate_salida)
    grafo.add_node("respuesta_segura", _nodo_respuesta_segura)
    grafo.add_node("respuesta_ok", _nodo_respuesta_ok)

    grafo.add_edge(START, "gate_entrada")
    grafo.add_conditional_edges(
        "gate_entrada", _routing_entrada, {"bloqueado": "respuesta_segura", "permitido": "agente"}
    )
    grafo.add_edge("agente", "gate_salida")
    grafo.add_conditional_edges(
        "gate_salida", _routing_salida, {"bloqueado": "respuesta_segura", "permitido": "respuesta_ok"}
    )
    grafo.add_edge("respuesta_segura", END)
    grafo.add_edge("respuesta_ok", END)
    return grafo.compile()


_app = _construir_grafo()


def responder(user_id: str, pregunta: str) -> str:
    """Punto de entrada usado por la API (main.py). Corre el grafo completo:
    guarda de entrada → agente → guarda de salida.

    El flush() se hace UNA vez acá, después de que el grafo completo terminó
    — no dentro de cada nodo — para que cubra también los casos donde el
    grafo termina temprano (bloqueado en gate_entrada, sin llegar al nodo
    'agente'). Si el flush viviera solo en el nodo del agente, esos casos
    bloqueados nunca enviarían su traza a Langfuse."""
    resultado = _app.invoke({"user_id": user_id, "pregunta": pregunta})

    if _LANGFUSE_ACTIVO and _langfuse_client:
        _langfuse_client.flush()

    return resultado["respuesta_final"]





