"""FastAPI que expone el agente (stage 0 · esqueleto).

Contrato: POST /chat {"user_id": "...", "pregunta": "..."} -> {"respuesta": "..."}

user_id identifica el hilo de conversación (memoria). En stage 0 no hay
autenticación real — cualquier string sirve como user_id (ej. un UUID que
genere el front). Eso es aceptable para este proyecto educativo, pero vale
la pena anotarlo en el informe como limitación conocida.
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv(override=True) 

logger = logging.getLogger("asistente-farmacias")

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("Falta OPENAI_API_KEY en tu .env (copia .env.example a .env y complétalo).")

# Import diferido a después de load_dotenv() / la validación de arriba,
# para que el error de env var salga ANTES de intentar construir el agente.
from asistente_farmacias.agent.graph import responder  # noqa: E402


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


@app.get("/")
def health():
    """Liveness check."""
    return {"status": "ok", "service": "asistente-farmacias", "stage": 0, "docs": "/docs"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Responde una pregunta, manteniendo memoria por user_id."""
    try:
        respuesta = responder(request.user_id, request.pregunta)
    except Exception:
        logger.exception("Fallo al responder la pregunta")
        raise HTTPException(status_code=502, detail="Fallo interno; revisa los logs del servidor.")
    return ChatResponse(respuesta=respuesta)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
