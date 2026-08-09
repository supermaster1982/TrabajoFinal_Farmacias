"""
resilience.py — Resiliencia ante caída o retiro forzoso de un modelo de LLM.

Por qué esto NO es hipotético: OpenAI ya retiró gpt-4o-mini públicamente
(lo vivimos en este mismo proyecto — tuvimos que migrar a gpt-5.4-mini).
Y más reciente: Anthropic suspendió temporalmente el acceso a Claude Fable 5
y Mythos 5 por controles de exportación de EE.UU. en julio 2026, restaurado
después. Un proyecto que depende de UN solo modelo, sin plan de respaldo,
puede quedar fuera de servicio de un día para otro sin que el equipo haya
hecho nada mal — es un riesgo del proveedor, no del código.

CADENA_MODELOS: orden de preferencia. Se intenta el primero; si falla
(modelo no encontrado/retirado, error del proveedor, timeout), se prueba
el siguiente. Si TODOS fallan, se propaga la excepción — el llamador
decide qué hacer (en las guardas de clinical_gate.py, fail-closed: si
ningún modelo responde, se bloquea por seguridad en vez de dejar pasar).
"""

import logging
import os

from langchain_openai import ChatOpenAI

logger = logging.getLogger("asistente-farmacias.resilience")

# Orden de preferencia. El primero es el que usa el proyecto normalmente;
# los siguientes son respaldo si el proveedor lo retira o falla.
#
# OJO: evitamos deliberadamente la familia GPT-4o/4.1 como respaldo — OpenAI
# ya las retiró de ChatGPT en febrero 2026 (junto con GPT-5 Instant/Thinking
# originales); aunque la API todavía las sostenga "por ahora", no tiene
# sentido usar como "plan B" algo que está en el mismo camino de salida que
# el modelo que reemplaza. Nos quedamos dentro de la familia GPT-5.x vigente.

# Modelo de las GUARDAS — variable propia, independiente de GEN_MODEL (el
# del agente). Antes leía GEN_MODEL por error, lo que acoplaba sin querer
# el modelo del agente con el de las guardas — descubierto al comparar
# modelos para el agente y notar que las guardas también cambiaban de
# comportamiento sin haberlo pedido.
CADENA_MODELOS = [
    os.getenv("GUARD_MODEL", "gpt-5.6-luna"),
    "gpt-5.4-mini",
    "gpt-5.4-nano",
]


def invocar_con_fallback(prompt: str, *, temperature: float = 0, config: dict | None = None, schema=None):
    """Intenta cada modelo de la cadena, en orden, hasta que uno responda.

    schema: si se pasa una clase Pydantic, usa with_structured_output. Ya
    no se usa en clinical_gate.py (ver docstring del módulo, causaba falsos
    bloqueos por moderación) pero se deja disponible por si otro caso de
    uso lo necesita.

    Algunos modelos (ej. gpt-5-mini) no aceptan temperature distinto al
    default (1) — si eso falla, reintenta el MISMO modelo sin fijar
    temperature, antes de pasar al siguiente de la cadena.

    Los modelos de la familia gpt-5.6.x son "razonadores" — rechazan con
    error 400 cualquier llamada que use function tools por
    /v1/chat/completions a menos que se les pase reasoning_effort="none"
    explícitamente (mismo límite ya documentado y resuelto en graph.py
    para GEN_MODEL, ver Fix #2).

    Devuelve la respuesta del primer modelo que funcione. Si todos fallan,
    lanza RuntimeError con el detalle del último error."""
    ultimo_error = None
    for i, modelo in enumerate(CADENA_MODELOS):
        # kwargs base para este modelo. Los razonadores (gpt-5.6.x)
        # necesitan reasoning_effort="none" para poder usar function tools.
        kwargs_base = {}
        if modelo.startswith("gpt-5.6"):
            kwargs_base["reasoning_effort"] = "none"

        # Primer intento: con la temperature pedida.
        # Segundo intento (mismo modelo): sin fijar temperature, por si el
        # modelo no soporta el valor pedido.
        for intento, kwargs_temp in enumerate([{"temperature": temperature}, {}]):
            kwargs = {**kwargs_base, **kwargs_temp}
            try:
                llm = ChatOpenAI(model=modelo, **kwargs)
                if schema is not None:
                    llm = llm.with_structured_output(schema)
                resultado = llm.invoke(prompt, config=config)
                if i > 0:
                    logger.warning(f"Modelo principal falló; respondió el fallback '{modelo}'.")
                return resultado
            except Exception as e:
                ultimo_error = e
                if intento == 0 and "temperature" in str(e).lower():
                    logger.warning(f"Modelo '{modelo}' no acepta temperature={temperature}, reintentando sin fijarla.")
                    continue
                logger.warning(f"Modelo '{modelo}' falló ({e!r}); probando el siguiente de la cadena.")
                break

    raise RuntimeError(
        f"Todos los modelos de la cadena fallaron ({CADENA_MODELOS}). "
        f"Último error: {ultimo_error!r}"
    )
