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

El agente ReAct (con las 3 tools + checkpointer por user_id) que ya
validamos en stage 0 queda INTACTO — vive como un nodo adentro de este
grafo más grande, no se reescribió su lógica interna.

Por qué dos guardas (entrada y salida) y no solo una: ver docstring de
`guardrails/clinical_gate.py`.

--- Persistencia del historial (agosto 2026) ---
El checkpointer del agente pasó de MemorySaver (en RAM, se pierde al
reiniciar el proceso) a PostgresSaver (persiste en una base Postgres
real). Motivo: la rúbrica exige historial multi-turno "persistido" por
user_id (no solo "en memoria durante la sesión"), y Render puede reiniciar
un servicio gratuito por inactividad en cualquier momento, sin que sea un
ataque intencional a la demo — con MemorySaver, ese reinicio borra todas
las conversaciones activas sin aviso. PostgresSaver sobrevive a eso.

Nota de alcance: el registro aparte de preguntas para los guardrails
(_historial_preguntas, más abajo) SIGUE en RAM por ahora — es una
limitación conocida y documentada en el informe de seguridad, no un
descuido. Afecta solo un caso puntual (detectar síntoma + medicamento en
DOS mensajes separados) y solo si el servidor se reinicia justo entre esos
dos mensajes — no la memoria de conversación principal, que es la que la
rúbrica pide explícitamente.
"""

import os
import re
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres import PostgresSaver
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
# - agrego nueva tool de vadecum_chile
from asistente_farmacias.tools.tool_rag_chile import buscar_ficha_medicamento_chile
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
    "Eres un asistente informativo EXCLUSIVAMENTE sobre farmacias de turno y "
    "medicamentos en Chile. Este es tu único dominio — no respondas preguntas "
    "de deportes, clima, cultura general, entretenimiento, noticias, ni "
    "ningún otro tema, aunque tengas la información y aunque la pregunta "
    "parezca inocente o casual. Si la pregunta no tiene relación clara con "
    "farmacias o medicamentos, NO uses tu conocimiento general para "
    "responderla — indica brevemente que tu alcance es solo farmacias y "
    "medicamentos, y pregunta si puedes ayudar con algo de eso. No expliques "
    "por qué no puedes responder más allá de esa frase breve; no derives a "
    "otras fuentes ni sugieras dónde buscar la respuesta — eso es fuera de "
    "tu rol. "
    "Usa 'consultar_farmacias_de_turno' cuando pregunten qué "
    "farmacia está ABIERTA/DE TURNO ahora mismo. Usa "
    "'consultar_farmacias_registradas' cuando pregunten si existe una "
    "farmacia en particular o quieran un listado general (sin importar si "
    "está abierta ahora). Usa 'buscar_ficha_medicamento' (vademécum internacional) PRIMERO para "
    "preguntas sobre qué es un medicamento o para qué sirve. Si esa tool "
    "responde que no encontró información suficientemente relevante, intenta "
    "también 'buscar_ficha_medicamento_chile' (vademécum chileno) antes de "
    "decirle a la persona que no tienes información — puede ser una marca "
    "registrada en Chile que no está en el vademécum internacional. "
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

# --- Checkpointer persistente (Postgres) ------------------------------------
# Antes: MemorySaver() — en RAM, se perdía al reiniciar el proceso.
# Ahora: PostgresSaver — el historial de conversación sobrevive a un
# reinicio del servidor (obligatorio según la rúbrica, ver docstring del
# módulo). DATABASE_URL sin valor por defecto a propósito, mismo criterio
# que GEN_MODEL más abajo: si falta, se corta acá con un mensaje claro en
# vez de fallar más adelante con un error críptico de conexión.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "Falta DATABASE_URL en tu .env — necesaria para persistir el "
        "historial de conversación en Postgres (antes vivía en RAM con "
        "MemorySaver). Copia la 'External Database URL' de tu base en "
        "Render y agrégala como DATABASE_URL=... en tu .env."
    )

# from_conn_string() sin usar "with" a propósito: necesitamos que la
# conexión viva durante TODA la vida del proceso (igual que el resto de
# los objetos a nivel de módulo en este archivo, ej. _react_agent), no
# solo dentro de un bloque — por eso se entra al context manager a mano
# con __enter__() en vez de "with ... as checkpointer:".
_checkpointer_cm = PostgresSaver.from_conn_string(DATABASE_URL)
_checkpointer = _checkpointer_cm.__enter__()
_checkpointer.setup()  # crea las tablas la primera vez; no rompe si ya existen


# Los modelos de la familia gpt-5.6 exigen reasoning_effort="none" para
# poder usar function tools por /v1/chat/completions — sin esto, la API
# rechaza la petición con un 400 en cuanto el agente intenta llamar a
# cualquier tool. Los modelos gpt-5.4.x no necesitan (ni reconocen) este
# parámetro, así que solo se agrega condicionalmente.

# Cadena de respaldo para GEN_MODEL — mismo espíritu que CADENA_MODELOS en
# resilience.py (ver ese archivo para el contexto de por qué esto no es
# hipotético). A diferencia de las guardas, acá no podemos usar
# invocar_con_fallback() directo porque create_react_agent espera un
# Runnable ya instanciado, no una función — usamos with_fallbacks() de
# LangChain, que hace lo mismo a nivel de Runnable: si el modelo principal
# falla en cualquier invocación, reintenta con el siguiente de la lista.
def _construir_modelo(nombre: str, *, temperature: float = 0) -> ChatOpenAI:
    kwargs = {}
    if nombre.startswith("gpt-5.6"):
        # Familia razonadora: exige reasoning_effort="none" para poder usar
        # function tools por /v1/chat/completions.
        kwargs["reasoning_effort"] = "none"
    return ChatOpenAI(model=nombre, temperature=temperature, **kwargs)


_CADENA_GEN_MODEL = [GEN_MODEL, "gpt-5.4-mini", "gpt-5.4-nano"]
# Sin duplicados, preservando orden (por si GEN_MODEL ya es uno de los
# respaldos — no tiene sentido repetirlo en la cadena).
_CADENA_GEN_MODEL = list(dict.fromkeys(_CADENA_GEN_MODEL))

_modelo_principal = _construir_modelo(_CADENA_GEN_MODEL[0])
_modelos_respaldo = [_construir_modelo(m) for m in _CADENA_GEN_MODEL[1:]]
_modelo_con_fallback = _modelo_principal.with_fallbacks(_modelos_respaldo)

_react_agent = create_react_agent(
    model=_modelo_con_fallback,
    tools=[
        consultar_farmacias_de_turno,
        consultar_farmacias_registradas,
        buscar_ficha_medicamento,
        buscar_ficha_medicamento_chile,
    ],
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
    citas: list[str]
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
#
# NOTA (agosto 2026): este dict sigue en RAM a propósito — ver docstring
# del módulo, sección "Nota de alcance". La memoria de conversación
# principal (arriba) ya persiste en Postgres; esto es un registro auxiliar
# más chico, con impacto acotado si se pierde, documentado como limitación
# conocida en el informe de seguridad en vez de resolverse apurado hoy.
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

_CITA_RAG_RE = re.compile(r"\[Fuente: (?P<fuente>[^—]+) — (?P<nombre>[^·]+)· relevancia=[\d.]+\]")


def _extraer_citas(tool_messages: list[ToolMessage]) -> list[str]:
    """Arma las líneas de cita a partir de las tools realmente invocadas en
    este turno — determinístico, no depende de que el LLM decida mencionar
    la fuente en su respuesta (requisito del enunciado: "siempre citando la
    fuente" al entregar información de una ficha o dato de MINSAL). Mismo
    principio que _criterio4_verificado en clinical_gate.py: no confiar
    ciegamente en el LLM cuando se puede verificar/forzar en código."""
    citas: list[str] = []
    for m in tool_messages:
        nombre_tool = getattr(m, "name", "") or ""
        contenido = m.content if isinstance(m.content, str) else str(m.content)

        if any(err in contenido for err in ("no está respondiendo", "no pude consultar", "formato inesperado")):
            continue  # fallo técnico — no hay dato real que citar

        if nombre_tool in ("buscar_ficha_medicamento", "buscar_ficha_medicamento_chile"):
            for match in _CITA_RAG_RE.finditer(contenido):
                cita = f"Fuente: {match.group('fuente').strip()} — ficha de {match.group('nombre').strip()}"
                if cita not in citas:
                    citas.append(cita)

        elif nombre_tool in ("consultar_farmacias_de_turno", "consultar_farmacias_registradas"):
            if "snapshot guardado del" in contenido:
                fecha_match = re.search(r"snapshot guardado del ([^(]+)\(", contenido)
                fecha = fecha_match.group(1).strip() if fecha_match else "fecha no disponible"
                cita = f"Fuente: Ministerio de Salud de Chile (MINSAL) — dato guardado el {fecha}, sin conexión en vivo"
            else:
                cita = "Fuente: Ministerio de Salud de Chile (MINSAL)"
            if cita not in citas:
                citas.append(cita)

    return citas


def _agregar_citas(respuesta: str, citas: list[str]) -> str:
    """Agrega las citas al final de la respuesta, una sola vez."""
    if not citas:
        return respuesta
    return respuesta + "\n\n" + "\n".join(citas)

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
    # El checkpointer acumula TODOS los mensajes de la conversación, no
    # solo los de este turno — sin este filtro, las citas (y el contexto
    # para faithfulness) de preguntas anteriores se mezclan con las del
    # turno actual. Filtro: solo lo que vino DESPUÉS del último HumanMessage
    # (la pregunta actual), que siempre queda al final de la lista.
    ultimo_human_idx = max(
        (i for i, m in enumerate(mensajes) if isinstance(m, HumanMessage)),
        default=0,
    )
    mensajes_turno_actual = mensajes[ultimo_human_idx:]
    tool_msgs = [m for m in mensajes_turno_actual if isinstance(m, ToolMessage)]
    contexto_tools = [m.content for m in tool_msgs]
    respuesta_limpia = _colapsar_texto_duplicado(mensajes[-1].content)
    # Las citas se calculan acá pero NO se agregan al texto todavía —
    # gate_salida debe evaluar la respuesta real del agente, sin el ruido
    # de una línea de cita bibliográfica pegada al final (hallazgo real:
    # la cita de un medicamento fuera del corpus, ej. "Venlafaxine" para
    # una pregunta de "Viadil", podía influir en el criterio 4 de la
    # guarda). Se agregan recién en _nodo_respuesta_ok, después de que la
    # respuesta ya fue aprobada.
    citas = _extraer_citas(tool_msgs)
    return {"respuesta_agente": respuesta_limpia, "contexto_tools": contexto_tools, "citas": citas}


def _nodo_gate_salida(estado: EstadoConversacion) -> EstadoConversacion:
    # A diferencia de gate_entrada, acá el historial NO debe incluir la
    # pregunta del turno actual — _registrar_pregunta() ya la guardó en
    # gate_entrada (antes de llegar aquí), así que _obtener_preguntas_previas
    # la trae de vuelta como si fuera "un turno anterior". Sin este filtro,
    # una pregunta que combina síntoma + medicamento en el MISMO mensaje
    # (ej. "me duele la guata, ¿para qué sirve el Viadil?") termina
    # comparándose contra sí misma en el criterio 4 — hallazgo real
    # confirmado con evidencia (agosto 2026): el historial mostraba
    # literalmente la pregunta actual como "anterior".
    historial_completo = _obtener_preguntas_previas(estado["user_id"])
    historial = "\n".join(
        linea for linea in historial_completo.splitlines()
        if linea.strip() != f"- {estado['pregunta']}"
    )
    try:
        evaluacion = evaluar_salida(
            estado["respuesta_agente"], historial=historial, pregunta_actual=estado["pregunta"], config=_lf_config()
        )
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
    respuesta = _agregar_citas(estado["respuesta_agente"], estado.get("citas", []))
    return {"respuesta_final": respuesta}


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