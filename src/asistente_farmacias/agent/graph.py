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
import re
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import ToolMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from collections import defaultdict

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

GEN_MODEL = os.getenv("GEN_MODEL")
if not GEN_MODEL:
    raise RuntimeError(
        "Falta GEN_MODEL en tu .env — indica qué modelo usa el agente "
        "(ej. GEN_MODEL=gpt-5.4-mini). No tiene valor por defecto a "
        "propósito: así siempre queda explícito y trazable qué modelo se "
        "está usando, en vez de depender de un valor escondido en el código."
    )

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
    "No inventes información que las herramientas no te dieron. "
    "Nunca recomiendas medicamentos, dosis, ni tratamientos. "
    "Si una tool falla o no puede consultar datos, informa la falla con "
    "claridad y ofrece reintentar o derivar — NUNCA completes la respuesta "
    "usando tu propio conocimiento general como reemplazo, aunque lo "
    "sepas; la respuesta debe basarse únicamente en lo que la herramienta devolvió. "
    "Si la persona mencionó un síntoma o malestar personal (dolor, molestia, "
    "etc.) en cualquier momento de esta conversación (turno actual o "
    "anterior), incluye UNA SOLA VEZ, al principio de tu respuesta, una "
    "frase breve sugiriendo que consulte a un profesional de salud para "
    "evaluar ese síntoma — no repitas ni reformules esa sugerencia más de "
    "una vez en la misma respuesta. Después de esa única frase, puedes dar "
    "la información general del medicamento que te pregunten, sin decir "
    "que ese medicamento es lo indicado para su síntoma. "
    "Si el mensaje de la persona es solo la mención de un síntoma o "
    "malestar, sin pedir nada específico (sin nombrar un medicamento, sin "
    "pedir una farmacia, sin preguntar nada en concreto), NO uses ninguna "
    "tool — responde directamente con la sugerencia de evaluación "
    "profesional, y pregunta qué le gustaría saber (ej. información de un "
    "medicamento en particular, o una farmacia de turno). Nunca busques el "
    "nombre del síntoma como si fuera un medicamento."
)

_checkpointer = MemorySaver()


# Los modelos de la familia gpt-5.6 exigen reasoning_effort="none" para
# poder usar function tools por /v1/chat/completions — sin esto, la API
# rechaza la petición con un 400 en cuanto el agente intenta llamar a
# cualquier tool. Los modelos gpt-5.4.x no necesitan (ni reconocen) este
# parámetro, así que solo se agrega condicionalmente.
_kwargs_modelo = {}
if GEN_MODEL.startswith("gpt-5.6"):
    _kwargs_modelo["reasoning_effort"] = "none"

_react_agent = create_react_agent(
    model=ChatOpenAI(model=GEN_MODEL, temperature=0, **_kwargs_modelo),
    tools=[consultar_farmacias_de_turno, consultar_farmacias_registradas, buscar_ficha_medicamento],
    prompt=SYSTEM_PROMPT,
    checkpointer=_checkpointer,
)


class EstadoConversacion(TypedDict, total=False):
    user_id: str
    pregunta: str
    bloqueado_en_entrada: bool
    razon_entrada: str
    fallo_tecnico_entrada: bool
    respuesta_agente: str
    contexto_tools: list[str]
    bloqueado_en_salida: bool
    razon_salida: str
    fallo_tecnico_salida: bool
    respuesta_final: str


def _lf_config() -> dict:
    """Config de Langfuse a reutilizar en cada nodo que llama a un LLM
    (guarda de entrada, agente, guarda de salida) — así TODAS las llamadas
    quedan trazadas, no solo la del agente. Esto importa especialmente para
    los casos BLOQUEADOS: si el guardrail nunca traza su propia decisión,
    la demo no puede mostrar evidencia de que el bloqueo realmente ocurrió."""
    return {"callbacks": [_langfuse_handler]} if _langfuse_handler else {}

# Registro propio de preguntas por conversación — separado del checkpointer
# del agente. Por qué: el checkpointer SOLO se actualiza cuando el agente
# corre de verdad — si una pregunta es bloqueada por gate_entrada, el
# agente nunca se ejecuta y esa pregunta nunca queda guardada ahí. Como
# justo las preguntas bloqueadas (por mencionar un síntoma) son las más
# importantes de recordar, necesitamos un registro que capture TODO lo que
# llega, sin importar si después se bloquea o no.
_historial_preguntas: dict[str, list[str]] = defaultdict(list)


def _registrar_pregunta(user_id: str, pregunta: str, max_preguntas: int = 4) -> None:
    _historial_preguntas[user_id].append(pregunta)
    _historial_preguntas[user_id] = _historial_preguntas[user_id][-max_preguntas:]


def _obtener_preguntas_previas(user_id: str) -> str:
    """Devuelve las preguntas anteriores registradas para ese user_id (sin
    contar la actual). "" si es la primera pregunta de la conversación."""
    preguntas = _historial_preguntas.get(user_id, [])
    if not preguntas:
        return ""
    return "\n".join(f"- {p}" for p in preguntas)
    
def _colapsar_texto_duplicado(texto: str) -> str:
    """A veces el modelo repite literalmente el mismo texto dos veces
    seguidas en su respuesta (bug de comportamiento del LLM con este
    prompt, no de nuestro código — persiste incluso pidiéndole
    explícitamente 'una sola vez'). Esta función detecta y recorta esa
    repetición exacta, sin tocar el resto del texto ni afectar respuestas
    normales sin duplicación."""
    texto = texto.strip()

    # Caso 1: el mensaje completo son 2 copias idénticas seguidas.
    match = re.fullmatch(r"(?P<frase>.+?)\s+(?P=frase)\s*", texto, re.DOTALL)
    if match:
        return match.group("frase").strip()

    # Caso 2: solo la primera oración se repite al principio.
    match = re.match(r"^(?P<frase>.{10,300}?[.!?])\s+(?P=frase)\s*", texto)
    if match:
        resto = texto[match.end():].strip()
        return f"{match.group('frase')} {resto}".strip() if resto else match.group("frase")

    return texto

def _nodo_gate_entrada(estado: EstadoConversacion) -> EstadoConversacion:
    historial = _obtener_preguntas_previas(estado["user_id"])
    try:
        evaluacion = evaluar_entrada(estado["pregunta"], historial=historial, config=_lf_config())
        print(f"🚦 gate_entrada · bloqueado={evaluacion.es_peligroso} · razón: {evaluacion.razon}")
        return {
            "bloqueado_en_entrada": evaluacion.es_peligroso,
            "razon_entrada": evaluacion.razon,
            "fallo_tecnico_entrada": False,
        }
    except Exception as e:
        print(f"⚠️ gate_entrada FALLÓ (fail-closed): {e!r}")
        return {
            "bloqueado_en_entrada": True,
            "razon_entrada": f"Guarda de entrada falló ({e!r}); fail-closed.",
            "fallo_tecnico_entrada": True,
        }
    finally:
        # Se registra SIEMPRE, sin importar si esta pregunta terminó
        # bloqueada o no — para que el próximo turno la recuerde igual.
        _registrar_pregunta(estado["user_id"], estado["pregunta"])


def _nodo_agente(estado: EstadoConversacion) -> EstadoConversacion:
    config = {
        "configurable": {"thread_id": estado["user_id"]},
        "recursion_limit": 12,  # freno contra gasto de tokens sin control (una pregunta normal usa 2-4 pasos)
        **_lf_config(),
    }
    try:
        resultado = _react_agent.invoke(
            {"messages": [{"role": "user", "content": estado["pregunta"]}]}, config=config
        )
    except GraphRecursionError:
        # El agente se pasó del límite de pasos — algo anormal (bucle, o un
        # intento de manipular la pregunta para que siga pidiendo tools sin
        # parar). Se corta acá con un mensaje razonable, en vez de dejar que
        # LangGraph lance un error feo o siga gastando tokens sin fin.
        print("⚠️ agente alcanzó el límite de iteraciones (recursion_limit=12) — cortado por seguridad de costos")
        return {
            "respuesta_agente": (
                "No pude completar tu consulta en un número razonable de pasos. "
                "Intenta reformular tu pregunta de forma más específica, o vuelve a intentarlo."
            ),
            "contexto_tools": [],
        }

    mensajes = resultado["messages"]
    contexto_tools = [m.content for m in mensajes if isinstance(m, ToolMessage)]
    respuesta_limpia = _colapsar_texto_duplicado(mensajes[-1].content)
    return {"respuesta_agente": respuesta_limpia, "contexto_tools": contexto_tools}


def _nodo_gate_salida(estado: EstadoConversacion) -> EstadoConversacion:
    historial = _obtener_preguntas_previas(estado["user_id"])
    try:
        evaluacion = evaluar_salida(estado["respuesta_agente"], historial=historial, config=_lf_config())
        print(f"🚦 gate_salida · bloqueado={evaluacion.es_peligroso} · razón: {evaluacion.razon}")
        return {
            "bloqueado_en_salida": evaluacion.es_peligroso,
            "razon_salida": evaluacion.razon,
            "fallo_tecnico_salida": False,
        }
    except Exception as e:
        print(f"⚠️ gate_salida FALLÓ (fail-closed): {e!r}")
        return {
            "bloqueado_en_salida": True,
            "razon_salida": f"Guarda de salida falló ({e!r}); fail-closed.",
            "fallo_tecnico_salida": True,
        }


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


class GuardaNoDisponibleError(Exception):
    """Se lanza cuando una guarda de seguridad no pudo evaluar por una falla
    técnica (proveedor caído, credenciales inválidas, etc.) — distinto de
    un bloqueo real por contenido. main.py la traduce a un error HTTP
    honesto (503), en vez de devolver el mensaje de rechazo como si la
    petición hubiera sido evaluada y rechazada normalmente."""


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

    fallo_tecnico = resultado.get("fallo_tecnico_entrada", False) or resultado.get("fallo_tecnico_salida", False)
    if fallo_tecnico:
        raise GuardaNoDisponibleError(
            "El control de seguridad no pudo evaluar la pregunta en este momento "
            "(falla del proveedor del modelo). Por seguridad, no se procesó la "
            "solicitud. Intenta de nuevo en un momento."
        )

    return resultado["respuesta_final"]

def responder_con_contexto(user_id: str, pregunta: str) -> dict:
    """Variante de responder() SOLO para evaluación (eval_langsmith.py) —
    además de la respuesta final, devuelve el contexto crudo que las tools
    devolvieron durante el turno. main.py sigue usando responder() tal
    cual, esta función no toca el camino de producción."""
    resultado = _app.invoke({"user_id": user_id, "pregunta": pregunta})

    if _LANGFUSE_ACTIVO and _langfuse_client:
        _langfuse_client.flush()

    fallo_tecnico = resultado.get("fallo_tecnico_entrada", False) or resultado.get("fallo_tecnico_salida", False)
    if fallo_tecnico:
        raise GuardaNoDisponibleError(
            "El control de seguridad no pudo evaluar la pregunta en este momento "
            "(falla del proveedor del modelo). Por seguridad, no se procesó la "
            "solicitud. Intenta de nuevo en un momento."
        )

    return {
        "respuesta": resultado["respuesta_final"],
        "contexto": resultado.get("contexto_tools", []),  # vacío si bloqueó en gate_entrada (nunca llegó a las tools)
    }