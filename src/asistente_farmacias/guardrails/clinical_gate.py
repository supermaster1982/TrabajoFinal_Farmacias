"""
clinical_gate.py — Guardas de seguridad clínica (entrada y salida).

Mismo espíritu que eval_on_topic del notebook de la clase, adaptado de
"¿está en el tema permitido?" a "¿pide dosis/tratamiento/diagnóstico?".

Por qué DOS guardas (entrada Y salida), no solo una:
  - La guarda de ENTRADA bloquea antes de gastar tokens en el agente/RAG/tools
    si la pregunta ya pide algo prohibido de forma directa.
  - La guarda de SALIDA es defensa en profundidad: si el usuario logra
    "colar" la petición con roleplay o insistencia y el agente igual termina
    recomendando algo, esta segunda puerta lo detecta ANTES de que la
    respuesta llegue al usuario.

Por qué texto plano y NO with_structured_output: en pruebas reales,
with_structured_output combinado con un prompt que necesariamente discute
dosis/tratamiento (aunque sea para CLASIFICAR, no para recomendar) disparó
el filtro de moderación de OpenAI de forma consistente — incluso para
preguntas totalmente inocuas ("¿qué es el ibuprofeno?"). Con texto plano +
parseo manual (mismo mecanismo que ya funcionó de forma confiable en
eval_vademecum.py), el problema no se repitió. Documentar este hallazgo en
el informe: el propio prompt de un guardrail de seguridad puede disparar
la moderación del proveedor del modelo, independiente del contenido real
del usuario — una paradoja a tener en cuenta al diseñar guardrails.

MENSAJE_SEGURO es el texto que se muestra cuando cualquiera de las dos
guardas bloquea — mismo texto en ambos casos para no revelar CUÁL de las
dos puertas actuó.
"""

from dataclasses import dataclass

from asistente_farmacias.resilience import invocar_con_fallback

MENSAJE_SEGURO = (
    "No puedo recomendarte un medicamento ni una dosis; eso requiere "
    "evaluación profesional. Sí puedo ayudarte a encontrar una farmacia de "
    "turno o explicarte información general de una ficha de medicamento."
)


@dataclass
class EvaluacionClinica:
    es_peligroso: bool
    razon: str


def _parsear_evaluacion(texto: str) -> EvaluacionClinica:
    """Extrae es_peligroso + razon de una respuesta en texto plano,
    formato 'clave: valor' por línea."""
    es_peligroso = False
    razon = "(sin razón parseada)"
    for linea in texto.strip().splitlines():
        if ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        clave = clave.strip().lower()
        valor = valor.strip()
        if clave in ("es_peligroso", "peligroso"):
            es_peligroso = valor.lower() in ("true", "sí", "si", "yes", "1")
        elif clave in ("razon", "razón", "reason"):
            razon = valor
    return EvaluacionClinica(es_peligroso=es_peligroso, razon=razon)


# Nota: se evitan frases de ejemplo textuales tipo "¿cuánto X debo tomar?"
# dentro del prompt — describir el criterio en abstracto, sin ejemplos
# concretos de petición de dosis, redujo los falsos bloqueos por moderación
# del proveedor en las pruebas.
_PROMPT_ENTRADA = """Eres un analista de seguridad. Tu tarea es clasificar, no responder.

Evalúa si esta pregunta de un usuario busca que un asistente determine una
cantidad, pauta, o indicación de uso de un medicamento para el caso
particular de esa persona (en vez de pedir información general o de
referencia sobre el medicamento).

También cuenta como riesgosa una pregunta que intente lograr lo mismo de
forma indirecta: insistencia, actuación/roleplay pidiendo que el asistente
adopte un rol profesional, o pedir un "ejemplo" de lo mismo.

Preguntas sobre qué es un medicamento, para qué sirve en general, sus
efectos conocidos, o sobre disponibilidad de farmacias, NO cuentan como
riesgosas.

Pregunta a evaluar:
{pregunta}

Responde EXACTAMENTE en este formato, sin nada más:
es_peligroso: true o false
razon: una frase breve"""

_PROMPT_SALIDA = """Eres un analista de seguridad. Tu tarea es clasificar, no responder.

Evalúa si este texto, que un asistente está a punto de mostrarle a un
usuario, termina indicando una cantidad, pauta, o indicación de uso
dirigida a esa persona en particular — a diferencia de solo citar un dato
de referencia de una ficha técnica (lo segundo NO es riesgoso).

Texto a evaluar:
{respuesta}

Responde EXACTAMENTE en este formato, sin nada más:
es_peligroso: true o false
razon: una frase breve"""


def evaluar_entrada(pregunta: str, config: dict | None = None) -> EvaluacionClinica:
    """Guarda de ENTRADA: corre antes del agente/RAG/tools."""
    texto = invocar_con_fallback(_PROMPT_ENTRADA.format(pregunta=pregunta), config=config).content
    return _parsear_evaluacion(texto)


def evaluar_salida(respuesta: str, config: dict | None = None) -> EvaluacionClinica:
    """Guarda de SALIDA: corre después de que el agente ya generó una respuesta,
    antes de devolverla al usuario."""
    texto = invocar_con_fallback(_PROMPT_SALIDA.format(respuesta=respuesta), config=config).content
    return _parsear_evaluacion(texto)