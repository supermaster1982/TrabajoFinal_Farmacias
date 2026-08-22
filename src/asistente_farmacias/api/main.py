"""FastAPI que expone el agente.

Contrato (pedido explícito de la rúbrica): POST /chat {"user_id": "...", "pregunta": "..."}
          -> {"respuesta": "...", "user_id": "..."}

Dos caminos para el user_id, según si viene el header Authorization:
  - CON token (ude POST /session): el user_id real es el firmado dentro del
    token, no el del body — si además viene user_id en el body, debe
    coincidir (403 si no). Evita que alguien use el user_id de otra persona.
  - SIN token: se usa el user_id del body tal cual, sin verificación de
    firma — satisface el contrato {user_id, pregunta} literal para poder
    probar la API directo, sin pasar por /session primero.

POST /session es opcional pero recomendado: genera un user_id amigable
(ej. "Valentina482", vía Faker) + un token JWT válido por 45 min FIJOS,
sin renovación — al vencer, /chat responde 401 y hay que pedir una sesión
nueva (memoria en blanco). Ver docs/por-que-user-id.md.
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
    user_id: str | None = Field(
        default=None,
        description=(
            "Opcional si mandas el header Authorization con un token de "
            "sesión válido (se usa el user_id firmado dentro del token, y "
            "si además mandas este campo, debe coincidir con ese). "
            "Obligatorio si NO mandas Authorization — permite probar la "
            "API directo con el contrato {user_id, pregunta}, sin pasar "
            "por /session primero."
        ),
    )


class ChatResponse(BaseModel):
    respuesta: str
    user_id: str  # el user_id real usado en este turno — útil para confirmar identidad
    # Ya no se devuelve un token renovado: la sesión dura 45 min fijos
    # desde que se creó (ver auth.py). Cuando expira, /chat responde 401
    # y el front debe pedir una sesión nueva.


class SessionResponse(BaseModel):
    user_id: str
    token: str


app = FastAPI(
    title="Asistente Informativo de Farmacias y Medicamentos",
    version="1.1.0-demo",
    description=(
        "API conversacional informativa sobre farmacias de turno en Chile "
        "y medicamentos. Consulta datos en vivo del MINSAL, utiliza búsqueda "
        "semántica mediante RAG sobre un vademécum, mantiene memoria por sesión "
        "y aplica guardrails de seguridad para no recomendar diagnósticos, "
        "tratamientos ni dosis."
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
    El front la llama al cargar si no tiene un token guardado, y también
    cada vez que la persona pide un nombre nuevo ("recargar") — en ese
    caso la conversación empieza de cero (nueva identidad = memoria nueva,
    no se puede renombrar una sesión existente sin perder su historial)."""
    user_id, token = auth.crear_sesion()
    return SessionResponse(user_id=user_id, token=token)


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

    if authorization and authorization.startswith("Bearer "):
        # Camino seguro: el user_id real viene del token firmado, no del
        # body — evita que alguien mande un user_id ajeno y se cuele en
        # la memoria de otra persona.
        token_recibido = authorization.removeprefix("Bearer ").strip()
        try:
            user_id = auth.verificar_sesion(token_recibido)
        except auth.TokenInvalidoError as e:
            raise HTTPException(status_code=401, detail=f"Sesión inválida o expirada: {e}. Llama de nuevo a POST /session.")
        if request.user_id and request.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="El user_id del body no coincide con el de tu sesión — no puedes usar el user_id de otra persona.",
            )
    elif request.user_id:
        # Camino directo: sin token, se acepta el user_id del body tal
        # cual — satisface el contrato POST {user_id, pregunta} pedido
        # explícitamente, para probar la API sin pasar por /session primero.
        # Sin verificación de firma en este camino: quien lo use así no
        # tiene la protección de que otro "adivine" su user_id (mismo
        # trade-off que cualquier API que acepta un ID plano en el body).
        user_id = request.user_id
    else:
        raise HTTPException(
            status_code=422,
            detail="Falta el user_id: manda 'user_id' en el body, o el header Authorization con un token de POST /session.",
        )

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

    return ChatResponse(user_id=user_id,respuesta=respuesta)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
