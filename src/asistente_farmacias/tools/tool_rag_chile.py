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

Hallazgo real (agosto 2026) — conexión nueva en cada llamada, no una
compartida: la primera versión de este archivo creaba UN solo
MultiServerMCPClient a nivel de módulo, reutilizado en cada pregunta.
Funcionaba para descubrir la tool al arrancar (ver el log del servidor MCP:
una sesión abierta y cerrada al importar), pero al invocarla de verdad
durante una pregunta real, la llamada NUNCA llegaba al servidor (sin
ninguna sesión nueva en el log del MCP) y el agente recibía un error
genérico. Causa probable: el cliente compartido conserva recursos internos
(ej. un cliente HTTP async) atados al event loop en el que se creó — como
ese cliente se obtuvo con asyncio.run() en un hilo aparte (ver _run_async
más abajo, necesario porque uvicorn --reload ya corre su propio loop), ese
loop se cierra apenas termina el hilo, dejando esos recursos inválidos
para cualquier llamada posterior desde el loop real de FastAPI.

Solución: cada llamada crea su PROPIO MultiServerMCPClient desde cero,
vive y muere dentro del mismo hilo/loop, sin nada compartido entre
invocaciones. Cuesta un poco de latencia extra por reconectar en cada
pregunta, aceptable para el volumen de este proyecto — la robustez importa
más que ese costo menor.
"""

import asyncio
import os
import threading

from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient

# MCP_VADEMECUM_CHILE_URL: la URL completa del servidor MCP. En local, con
# ambos servicios en la misma máquina, el valor por defecto (localhost)
# funciona sin configurar nada. En producción (Render u otro hosting), el
# MCP corre como un servicio aparte con su propia URL pública — hay que
# setear esta variable de entorno para que apunte ahí, en vez de asumir
# localhost. Pendiente: coordinar con el equipo cuando se despliegue el
# servidor MCP.
_MCP_URL = os.environ.get("MCP_VADEMECUM_CHILE_URL", "http://localhost:8803/mcp")


def _run_async(coro):
    """asyncio.run() falla con 'cannot be called from a running event loop'
    cuando uvicorn --reload ya tiene su propio loop activo (uvloop). Si ya
    hay un loop corriendo, se ejecuta la corrutina en un hilo aparte con su
    PROPIO loop nuevo; si no hay ninguno (caso normal), se usa asyncio.run()
    directo."""
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


async def _llamar_mcp(medicamento: str) -> str:
    """Conexión MCP nueva de punta a punta: se crea, se usa, se descarta —
    ver docstring del módulo para el hallazgo que motivó este diseño."""
    cliente = MultiServerMCPClient(
        {
            "vademecum_chile": {
                "transport": "streamable_http",
                "url": _MCP_URL,
            },
        }
    )
    herramientas = await cliente.get_tools()
    herramienta = next(h for h in herramientas if h.name == "buscar_ficha_medicamento_chile")
    return await herramienta.ainvoke({"medicamento": medicamento})


@tool
def buscar_ficha_medicamento_chile(medicamento: str) -> str:
    """Busca información general de un medicamento en el vademécum CHILENO
    (marcas y genéricos registrados en Chile: mecanismo de acción, modo de
    administración, contraindicaciones, efectos adversos), vía protocolo
    MCP. Úsala SOLO si 'buscar_ficha_medicamento' (vademécum internacional)
    ya respondió que no encontró información suficientemente relevante
    sobre ese medicamento — es la segunda fuente, no la primera. NUNCA
    para decidir una dosis para una persona ni indicar tratamiento."""
    try:
        return _run_async(_llamar_mcp(medicamento))
    except Exception as e:
        # Mismo texto ("no pude consultar") que ya reconoce _extraer_citas()
        # en graph.py para no agregar una cita cuando la tool falló técnicamente.
        return f"No pude consultar el vademécum chileno en este momento ({e!r})."