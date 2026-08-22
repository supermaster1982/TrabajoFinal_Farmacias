"""
servidor_vademecum_chile.py — Servidor MCP que expone la búsqueda del
vademécum chileno como una tool MCP, consumida por el agente vía
langchain-mcp-adapters (ver tool_rag_chile.py, ahora un cliente MCP).

Requisito del profesor: "si van a usar este vademécum, el acceso lo
implementen como API o MCP que sea consumido desde la llamada de la tool
por el asistente/agente" — se eligió MCP.

Este servidor NO reimplementa la búsqueda: reutiliza rag_subgrafo_chile.py
tal cual (retrieve -> filtro de similitud 0.54 -> verificación de
relevancia con LLM), la misma lógica ya validada con eval formal. Solo
agrega la capa de protocolo MCP encima — mismo principio de capas
(datos vs. transporte) discutido antes de implementar esto.

Uso:
    poetry run python servidor_vademecum_chile.py

Debe estar CORRIENDO antes de levantar la API principal (uvicorn) — el
cliente MCP (tool_rag_chile.py) se conecta a este servidor al importar el
módulo. Puerto configurable con MCP_PORT_VADEMECUM_CHILE (por defecto 8803).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv

load_dotenv()
CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5500",
)

from mcp.server.fastmcp import FastMCP

from asistente_farmacias.tools.rag_subgrafo_chile import invocar_subgrafo_chile
from starlette.requests import Request
from starlette.responses import JSONResponse

mcp = FastMCP(
    "VademecumChile",
    instructions=(
        "Busca información general de medicamentos registrados en Chile: "
        "principio activo, mecanismo de acción, modo de administración, "
        "contraindicaciones, efectos adversos. NUNCA para decidir una "
        "dosis para una persona ni indicar tratamiento."
    ),
    port=int(os.environ.get("MCP_PORT_VADEMECUM_CHILE", "8803")),
)

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "vademecum_chile",
        },
        headers={
            "Access-Control-Allow-Origin": CORS_ALLOWED_ORIGINS,
        },
    )



@mcp.tool(
    title="Buscar ficha de medicamento (Chile)",
    description=(
        "Busca información general de un medicamento en el vademécum "
        "chileno (marcas y genéricos registrados en Chile). Úsala SOLO si "
        "la fuente internacional (Kaggle) ya respondió que no encontró "
        "información suficientemente relevante — es la segunda fuente, no "
        "la primera."
    ),
)

def buscar_ficha_medicamento_chile(medicamento: str) -> str:
    """Misma firma y mismo formato de salida (incluida la cita
    '[Fuente: ... — ... · relevancia=...]') que la versión anterior de
    tool_rag_chile.py — así _extraer_citas() en graph.py sigue funcionando
    sin ningún cambio en el lado del agente."""
    try:
        filtradas = invocar_subgrafo_chile(medicamento)
    except Exception as e:
        return f"No pude consultar el vademécum chileno en este momento ({e!r})."

    if not filtradas:
        return (
            f"No encontré información suficientemente relevante sobre "
            f"'{medicamento}' tampoco en el vademécum chileno indexado."
        )

    bloques = []
    for ficha, score in filtradas:
        bloques.append(
            f"[Fuente: {ficha.metadata.get('fuente', 'vademécum chileno')} — "
            f"{ficha.metadata.get('nombre', '?')} · relevancia={score:.2f}]\n"
            f"{ficha.page_content}"
        )
    return "\n\n".join(bloques)

app = mcp.streamable_http_app()

if __name__ == "__main__":
    print("Iniciando servidor MCP VademecumChile…")
    try:
        mcp.run(transport="streamable-http")
    except KeyboardInterrupt:
        # Ctrl+C es la forma normal de detener este servidor — sin este
        # except, Python muestra un traceback largo del apagado interno
        # de anyio/asyncio que no aporta nada (no es un error real).
        print("\nServidor MCP VademecumChile detenido.")