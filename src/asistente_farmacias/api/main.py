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

--- request_id: idempotencia + trazabilidad (agosto 2026) ---
ChatRequest acepta un `request_id` opcional (UUID), generado por el front
una vez por pregunta. Sirve para dos cosas, no relacionadas con la memoria
de conversación (esa sigue viviendo en el checkpointer de graph.py):

1. Idempotencia: si el front reintenta la MISMA pregunta por un timeout de
   red (el usuario no volvió a escribir nada, fue un reintento automático),
   el mismo request_id llega dos veces. En vez de invocar el grafo de
   nuevo (gastando tokens y, peor, arriesgando una respuesta distinta la
   segunda vez), se devuelve la respuesta ya calculada la primera vez.

2. Trazabilidad end-to-end: el mismo request_id se manda como metadata al
   grafo (ver graph.py), que lo agrega a la traza de LangSmith/Langfuse —
   así una pregunta puntual se puede buscar por ese ID exacto tanto en los
   logs de consola como en la traza de observabilidad, sin tener que
   adivinar cuál de varias preguntas del mismo user_id fue.

La clave del cache de idempotencia es (user_id, request_id), NO solo
request_id — así una persona nunca puede recibir por accidente (o a
propósito) la respuesta cacheada de otra persona, aunque coincida el UUID
(prácticamente imposible, pero la separación es gratis y cierra esa
puerta). Cache en memoria (mismo criterio que el rate limiter de más
abajo): se pierde si el servidor se reinicia, aceptable porque solo cubre
reintentos de red de corto plazo (TTL de 5 min), no algo que necesite
sobrevivir un reinicio como sí lo necesita el historial de conversación.
"""

import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response, Request, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


load_dotenv(override=True)

logger = logging.getLogger("asistente-farmacias")

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        "Falta OPENAI_API_KEY en tu .env "
        "(copia .env.example a .env y complétalo)."
    )

# Import diferido a después de load_dotenv() / la validación de arriba,
# para que el error de env var salga ANTES de intentar construir el agente.
from asistente_farmacias.agent.graph import (  # noqa: E402
    GuardaNoDisponibleError,
    obtener_historial,
    responder,
)
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

    request_id: UUID | None = Field(
        default=None,
        description=(
            "Opcional. ID único por pregunta (no por sesión) — el front "
            "genera uno nuevo cada vez que se envía una pregunta. Si la "
            "misma pregunta se reintenta con el MISMO request_id (ej. "
            "timeout de red), se devuelve la respuesta ya calculada en "
            "vez de reprocesar. También sirve para encontrar esta "
            "pregunta puntual en las trazas de LangSmith/Langfuse."
        ),
    )


class ChatResponse(BaseModel):
    respuesta: str
    user_id: str


class SessionResponse(BaseModel):
    user_id: str
    token: str


class HistorialItem(BaseModel):
    tipo: str
    contenido: str


class HistorialResponse(BaseModel):
    user_id: str
    mensajes: list[HistorialItem]


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

security = HTTPBearer(auto_error=False)


# --- CORS -------------------------------------------------------------------
_cors_origins_env = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5500,http://127.0.0.1:5500",
)

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in _cors_origins_env.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Rate limiting ----------------------------------------------------------
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "20"))
RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")
)

_rate_limit_buckets: dict[str, list] = defaultdict(list)


def _verificar_rate_limit(client_ip: str) -> bool:
    ahora = time.time()

    timestamps = _rate_limit_buckets[client_ip]

    timestamps[:] = [
        timestamp
        for timestamp in timestamps
        if ahora - timestamp < RATE_LIMIT_WINDOW_SECONDS
    ]

    if len(timestamps) >= RATE_LIMIT_MAX:
        return False

    timestamps.append(ahora)

    return True


# --- Idempotencia -----------------------------------------------------------
IDEMPOTENCY_TTL_SECONDS = int(
    os.getenv("IDEMPOTENCY_TTL_SECONDS", "300")
)

_idempotency_cache: dict[tuple[str, str], dict] = {}


def _limpiar_cache_idempotencia_vencido() -> None:
    ahora = time.time()

    vencidos = [
        clave
        for clave, entrada in _idempotency_cache.items()
        if ahora - entrada["timestamp"] > IDEMPOTENCY_TTL_SECONDS
    ]

    for clave in vencidos:
        del _idempotency_cache[clave]


# ---------------------------------------------------------------------------
# HEALTH
# ---------------------------------------------------------------------------

@app.get("/")
def health():
    return {
        "status": "ok",
        "service": "asistente-farmacias",
        "stage": 0,
        "docs": "/docs",
    }


# ---------------------------------------------------------------------------
# SESIÓN
# ---------------------------------------------------------------------------

@app.post("/session", response_model=SessionResponse)
def crear_sesion():
    """Genera una sesión anónima nueva."""

    user_id, token = auth.crear_sesion()

    return SessionResponse(
        user_id=user_id,
        token=token,
    )


# ---------------------------------------------------------------------------
# HISTORIAL
# ---------------------------------------------------------------------------

@app.get("/historial", response_model=HistorialResponse)
def historial(
    authorization: str | None = Header(default=None),
):
    """Devuelve el historial de la sesión actual."""

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail=(
                "Falta el header Authorization con un token de sesión válido "
                "(POST /session primero)."
            ),
        )

    token_recibido = (
        authorization
        .removeprefix("Bearer ")
        .strip()
    )

    try:
        user_id = auth.verificar_sesion(token_recibido)

    except auth.TokenInvalidoError as exc:
        raise HTTPException(
            status_code=401,
            detail=(
                f"Sesión inválida o expirada: {exc}. "
                "Llama de nuevo a POST /session."
            ),
        )

    mensajes = obtener_historial(user_id)

    return HistorialResponse(
        user_id=user_id,
        mensajes=[
            HistorialItem(**mensaje)
            for mensaje in mensajes
        ],
    )


# ---------------------------------------------------------------------------
# CHAT
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    response: Response,
    http_request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """Responde una pregunta manteniendo memoria por sesión."""

    client_ip = (
        http_request.client.host
        if http_request.client
        else "unknown"
    )

    if not _verificar_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail=(
                f"Demasiadas solicitudes. "
                f"Máximo {RATE_LIMIT_MAX} por minuto — "
                "espera un momento."
            ),
        )

    # -----------------------------------------------------------------------
    # Identificación de la sesión
    # -----------------------------------------------------------------------

    if credentials:
        token_recibido = credentials.credentials

        try:
            user_id = auth.verificar_sesion(token_recibido)

        except auth.TokenInvalidoError as exc:
            raise HTTPException(
                status_code=401,
                detail=(
                    f"Sesión inválida o expirada: {exc}. "
                    "Llama de nuevo a POST /session."
                ),
            )

        if (
            request.user_id
            and request.user_id != user_id
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "El user_id del body no coincide con el de tu sesión — "
                    "no puedes usar el user_id de otra persona."
                ),
            )

    elif request.user_id:
        # Permite probar la API sin JWT.
        user_id = request.user_id

    else:
        raise HTTPException(
            status_code=422,
            detail=(
                "Falta el user_id: manda 'user_id' en el body, "
                "o el header Authorization con un token "
                "de POST /session."
            ),
        )

    # -----------------------------------------------------------------------
    # Idempotencia
    # -----------------------------------------------------------------------

    clave_idempotencia = (
        (user_id, str(request.request_id))
        if request.request_id
        else None
    )

    if clave_idempotencia:
        _limpiar_cache_idempotencia_vencido()

        entrada_cacheada = _idempotency_cache.get(
            clave_idempotencia
        )

        if entrada_cacheada:
            print(
                f"♻️ request_id {request.request_id} "
                f"repetido para {user_id} — "
                "devolviendo respuesta cacheada."
            )

            return ChatResponse(
                **entrada_cacheada["response"]
            )

    # -----------------------------------------------------------------------
    # Procesamiento
    # -----------------------------------------------------------------------

    inicio = datetime.now(timezone.utc)

    request_id_str = (
        str(request.request_id)
        if request.request_id
        else None
    )

    sufijo_log = (
        f" [request_id={request_id_str}]"
        if request_id_str
        else ""
    )

    print(
        f"🕐 [{inicio.isoformat()}] "
        f"Pregunta de {user_id}: "
        f"{request.pregunta}"
        f"{sufijo_log}"
    )

    try:
        respuesta = responder(
            user_id,
            request.pregunta,
            request_id=request_id_str,
        )

    except GuardaNoDisponibleError as exc:
        logger.warning(
            "Guarda no disponible: %s",
            exc,
        )

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    except Exception:
        logger.exception(
            "Fallo al responder la pregunta"
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Fallo interno; revisa los logs del servidor."
            ),
        )

    fin = datetime.now(timezone.utc)

    print(
        f"🕐 [{fin.isoformat()}] "
        f"Respondido "
        f"(tardó {(fin - inicio).total_seconds():.1f}s)"
        f"{sufijo_log}"
    )

    # -----------------------------------------------------------------------
    # Headers de trazabilidad
    # -----------------------------------------------------------------------

    response.headers["X-Timestamp-UTC"] = fin.isoformat()

    if request_id_str:
        response.headers["X-Request-ID"] = request_id_str

    respuesta_final = ChatResponse(
        user_id=user_id,
        respuesta=respuesta,
    )

    # -----------------------------------------------------------------------
    # Guardar respuesta en cache de idempotencia
    # -----------------------------------------------------------------------

    if clave_idempotencia:
        _idempotency_cache[clave_idempotencia] = {
            "timestamp": time.time(),
            "response": respuesta_final.model_dump(),
        }

    return respuesta_final


# ---------------------------------------------------------------------------
# EJECUCIÓN LOCAL
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )
