"""FastAPI que expone el agente.

Contrato: POST /session -> {"token": "..."}
          POST /chat {"pregunta": "..."} + header Authorization: Bearer <token>
          -> {"respuesta": "...", "token": "..."} (token renovado)

El user_id real viene del token de sesión verificado (auth.py), no del
body — evita que alguien pueda inventarse o adivinar el user_id de otra
persona. Ver docs/por-que-user-id.md para el razonamiento completo.
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


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
from asistente_farmacias.api import auth  # noqa: E402


class ChatRequest(BaseModel):
    pregunta: str = Field(..., description="Pregunta del usuario.")
    # user_id ya NO se recibe del cliente — se obtiene del token de sesión
    # verificado (ver /session y auth.py), para que nadie pueda inventarse
    # o adivinar el user_id de otra persona.


class ChatResponse(BaseModel):
    respuesta: str
    token: str  # token renovado — el front debe reemplazar el que tenía guardado


class SessionResponse(BaseModel):
    token: str


app = FastAPI(
    title="Asistente Informativo de Farmacias y Medicamentos",
    version="0.1.0-stage0",
    description=(
        "Stage 0 (esqueleto): valida routing del agente y memoria por user_id "
        "con tools STUB. Las integraciones reales (MINSAL, RAG) llegan en "
        "etapas siguientes."
    ),
)
security = HTTPBearer()

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


@app.post("/session", response_model=SessionResponse)
def crear_sesion():
    """Genera una sesión anónima nueva — sin login, sin datos personales.
    El front la llama solo si no tiene un token guardado todavía."""
    _, token = auth.crear_sesion()
    return SessionResponse(token=token)


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    response: Response,
    http_request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Responde una pregunta, manteniendo memoria por sesión."""
    client_ip = http_request.client.host if http_request.client else "unknown"
    if not _verificar_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Demasiadas solicitudes. Máximo {RATE_LIMIT_MAX} por minuto — espera un momento.",
        )


    token_recibido = credentials.credentials
    try:
        user_id = auth.verificar_sesion(token_recibido)
    except auth.TokenInvalidoError as e:
        raise HTTPException(status_code=401, detail=f"Sesión inválida o expirada: {e}. Llama de nuevo a POST /session.")

    inicio = datetime.now(timezone.utc)
    print(f"🕐 [{inicio.isoformat()}] Pregunta de {user_id}: {request.pregunta}")
    try:
        respuesta = responder(user_id, request.pregunta)
    except GuardaNoDisponibleError as e:
        logger.warning(f"Guarda no disponible: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        logger.exception("Fallo al responder la pregunta")
        raise HTTPException(status_code=502, detail="Fallo interno; revisa los logs del servidor.")
    fin = datetime.now(timezone.utc)
    print(f"🕐 [{fin.isoformat()}] Respondido (tardó {(fin - inicio).total_seconds():.1f}s)")

    response.headers["X-Timestamp-UTC"] = fin.isoformat()

    token_renovado = auth.renovar_sesion(user_id)
    return ChatResponse(respuesta=respuesta, token=token_renovado)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
