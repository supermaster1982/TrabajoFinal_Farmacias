"""FastAPI que expone el agente (stage 0 · esqueleto).

Contrato: POST /chat {"user_id": "...", "pregunta": "..."} -> {"respuesta": "..."}

user_id identifica el hilo de conversación (memoria). En stage 0 no hay
autenticación real — cualquier string sirve como user_id (ej. un UUID que
genere el front). Eso es aceptable para este proyecto educativo, pero vale
la pena anotarlo en el informe como limitación conocida.
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv(override=True)

logger = logging.getLogger("asistente-farmacias")

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("Falta OPENAI_API_KEY en tu .env (copia .env.example a .env y complétalo).")

# Import diferido a después de load_dotenv() / la validación de arriba,
# para que el error de env var salga ANTES de intentar construir el agente.
from asistente_farmacias.agent.graph import GuardaNoDisponibleError, responder  # noqa: E402


class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Identificador del usuario/conversación (memoria).")
    pregunta: str = Field(..., description="Pregunta del usuario.")


class ChatResponse(BaseModel):
    respuesta: str


app = FastAPI(
    title="Asistente Informativo de Farmacias y Medicamentos",
    version="0.1.0-stage0",
    description=(
        "Stage 0 (esqueleto): valida routing del agente y memoria por user_id "
        "con tools STUB. Las integraciones reales (MINSAL, RAG) llegan en "
        "etapas siguientes."
    ),
)

# CORS: permite que el front (un .html abierto en el navegador, o servido
# desde otro puerto) pueda llamar a esta API. "*" es suficientemente
# permisivo para desarrollo on-prem; si en algún momento se despliega en
# la nube, conviene restringir allow_origins al dominio real del front,
# no dejarlo abierto a cualquier origen en producción.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health():
    """Liveness check."""
    return {"status": "ok", "service": "asistente-farmacias", "stage": 0, "docs": "/docs"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, response: Response):
    """Responde una pregunta, manteniendo memoria por user_id."""
    inicio = datetime.now(timezone.utc)
    print(f"🕐 [{inicio.isoformat()}] Pregunta de {request.user_id}: {request.pregunta}")
    try:
        respuesta = responder(request.user_id, request.pregunta)
    except GuardaNoDisponibleError as e:
        # No es un rechazo real del guardrail — es una falla técnica que,
        # por diseño (fail-closed), bloqueó la respuesta. Se reporta como
        # un error real (503), no como si fuera una respuesta normal.
        logger.warning(f"Guarda no disponible: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        logger.exception("Fallo al responder la pregunta")
        raise HTTPException(status_code=502, detail="Fallo interno; revisa los logs del servidor.")
    fin = datetime.now(timezone.utc)
    print(f"🕐 [{fin.isoformat()}] Respondido (tardó {(fin - inicio).total_seconds():.1f}s)")

    # Header HTTP personalizado, visible en la pestaña "Headers" de /docs o
    # en curl -i — para cruzar directo contra la hora que muestra Langfuse.
    response.headers["X-Timestamp-UTC"] = fin.isoformat()

    return ChatResponse(respuesta=respuesta)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
