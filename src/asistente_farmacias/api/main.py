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
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import time
from collections import defaultdict


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

# --- CORS: configurable por .env, no abierto a cualquier origen -------------
# En desarrollo apunta a tu front local. Cuando despliegues, agrega la URL
# real de producción a CORS_ALLOWED_ORIGINS en el .env (separadas por coma),
# sin tocar código.
_cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rate limiting: ventana deslizante simple, en memoria --------------------
# Sin librería nueva ni infraestructura extra (Redis, etc.) — apropiado para
# este proyecto. Protege contra un cliente (o script) que golpee /chat sin
# límite, gastando créditos de OpenAI sin control.
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "20"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
_rate_limit_buckets: dict[str, list] = defaultdict(list)


def _verificar_rate_limit(client_ip: str) -> bool:
    ahora = time.time()
    timestamps = _rate_limit_buckets[client_ip]
    timestamps[:] = [t for t in timestamps if ahora - t < RATE_LIMIT_WINDOW_SECONDS]
    if len(timestamps) >= RATE_LIMIT_MAX:
        return False
    timestamps.append(ahora)
    return True

@app.get("/")
def health():
    """Liveness check."""
    return {"status": "ok", "service": "asistente-farmacias", "stage": 0, "docs": "/docs"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, response: Response, http_request: Request):
    """Responde una pregunta, manteniendo memoria por user_id."""
    client_ip = http_request.client.host if http_request.client else "unknown"
    if not _verificar_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Demasiadas solicitudes. Máximo {RATE_LIMIT_MAX} por minuto — espera un momento.",
        )

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
