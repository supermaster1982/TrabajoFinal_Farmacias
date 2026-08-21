"""
tool_rag_chile.py — Cliente MCP para el vademécum CHILENO.

Ya no llama directo a rag_subgrafo_chile.py — consume la búsqueda a través
del protocolo MCP, conectándose al servidor definido en
servidor_vademecum_chile.py (debe estar CORRIENDO antes de levantar la API
principal). Requisito del profesor: exponer esta fuente como API o MCP,
consumida desde la tool del agente — se eligió MCP.

Por qué un cliente y no la función directa: la lógica de búsqueda
(retrieve -> filtro de similitud 0.54 -> verificación de relevancia LLM)
sigue siendo exactamente la misma — rag_subgrafo_chile.py no se duplicó,
el servidor MCP solo la envuelve. Este archivo solo cambia CÓMO se llega
a ella: por protocolo MCP en vez de un import directo de Python, mismo
patrón de MultiServerMCPClient que protocolo_mcp.ipynb (Clase 5.4).

`create_react_agent` (en graph.py) construye su lista de tools al importar
el módulo — de forma síncrona — pero `MultiServerMCPClient.get_tools()` es
async. Se resuelve con asyncio.run() a nivel de módulo: corre UNA vez, al
importar, antes de que uvicorn levante su propio event loop — no en cada
request.
"""

import asyncio
import os
import threading

from langchain_mcp_adapters.client import MultiServerMCPClient

# MCP_VADEMECUM_CHILE_URL: la URL completa del servidor MCP. En local, con
# ambos servicios en la misma máquina, el valor por defecto (localhost)
# funciona sin configurar nada. En producción (Render u otro hosting), el
# MCP corre como un servicio aparte con su propia URL pública — hay que
# setear esta variable de entorno para que apunte ahí, en vez de asumir
# localhost. Pendiente: coordinar con el equipo cuando se despliegue el
# servidor MCP.
_MCP_URL = os.environ.get("MCP_VADEMECUM_CHILE_URL", "http://localhost:8803/mcp")

_cliente = MultiServerMCPClient(
    {
        "vademecum_chile": {
            "transport": "streamable_http",
            "url": _MCP_URL,
        },
    }
)


def _run_async(coro):
    """asyncio.run() falla con 'cannot be called from a running event loop'
    cuando uvicorn --reload ya tiene su propio loop activo (uvloop) al
    momento de importar este módulo — hallazgo real (agosto 2026), no
    ocurre con `uvicorn` sin --reload, pero sí con --reload, que se usa en
    desarrollo local. Si ya hay un loop corriendo, se ejecuta la corrutina
    en un hilo aparte con su PROPIO loop nuevo, para no anidar uno dentro
    de otro; si no hay ningún loop corriendo (caso normal), se usa
    asyncio.run() directo, sin este rodeo."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    resultado = {}
    error = {}

    def _en_hilo_aparte():
        try:
            resultado["valor"] = asyncio.run(coro)
        except Exception as e:
            error["excepcion"] = e

    hilo = threading.Thread(target=_en_hilo_aparte)
    hilo.start()
    hilo.join()

    if "excepcion" in error:
        raise error["excepcion"]
    return resultado["valor"]


def _cargar_tool_mcp():
    try:
        herramientas = _run_async(_cliente.get_tools())
    except Exception as e:
        raise RuntimeError(
            f"No se pudo conectar al servidor MCP de vademécum chileno en "
            f"{_MCP_URL} ({e!r}). ¿Está corriendo "
            f"'poetry run python servidor_vademecum_chile.py' en otra terminal? "
            f"Debe iniciarse ANTES que la API principal."
        ) from e

    try:
        return next(h for h in herramientas if h.name == "buscar_ficha_medicamento_chile")
    except StopIteration:
        raise RuntimeError(
            f"El servidor MCP en {_MCP_URL} respondió, pero no expone ninguna "
            f"tool llamada 'buscar_ficha_medicamento_chile'. Herramientas "
            f"encontradas: {[h.name for h in herramientas]}"
        )


# Nombre idéntico al de la versión anterior (implementación directa) — así
# graph.py no necesita ningún cambio: sigue importando
# 'buscar_ficha_medicamento_chile' desde este mismo módulo, y
# _extraer_citas() en graph.py sigue reconociendo el nombre de la tool tal
# cual, sin tocar esa lógica.
buscar_ficha_medicamento_chile = _cargar_tool_mcp()