"""
auth.py — Sesión anónima firmada (JWT), sin cuentas ni contraseñas.

Por qué esto y no un sistema de usuarios completo: ver docs/por-que-user-id.md.
Resumen: el user_id existe para 2 cosas — (1) que la memoria de la
conversación no se mezcle entre personas distintas, y (2) que las trazas
de observabilidad (LangSmith/Langfuse) no queden asociadas a datos
personales identificables. Ninguna de las dos razones requiere saber
QUIÉN es la persona — solo requiere un identificador que no se pueda
falsificar y que no contenga información personal.

Cómo funciona:
1. El front llama a POST /session la primera vez (sin login, sin datos).
2. El servidor genera un ID aleatorio (uuid4) y lo firma en un JWT.
3. El front guarda el token y lo manda en cada pregunta siguiente
   (Authorization: Bearer <token>).
4. /chat verifica la firma del token y usa el ID que viene DENTRO de él
   como el user_id/thread_id real — nunca confía en un user_id que el
   cliente intente mandar directamente sin pasar por este mecanismo.
"""

import os
import secrets
import time
import unicodedata

import jwt
from faker import Faker

_fake = Faker("es_CL")

SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY")
if not SESSION_SECRET_KEY:
    raise RuntimeError(
        "Falta SESSION_SECRET_KEY en tu .env. Genera una con:\n"
        "  python3 -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "y agrégala a tu .env como SESSION_SECRET_KEY=<lo que imprima>"
    )

_ALGORITMO = "HS256"
_EXPIRACION_SEGUNDOS = 45 * 60 # 45 min desde que se crea la sesión — fijo,
# no se renueva con el uso. Al vencer, /chat lo rechaza (401) y el front
# debe pedir una sesión nueva (nuevo user_id, memoria en blanco). Evita
# que un token robado quede útil indefinidamente mientras alguien lo siga
# usando cada cierto tiempo.


class TokenInvalidoError(Exception):
    """El token no existe, está mal formado, expiró, o la firma no coincide
    con nuestra SESSION_SECRET_KEY (alguien intentó falsificarlo)."""


def _firmar(session_id: str) -> str:
    ahora = int(time.time())
    payload = {"sid": session_id, "iat": ahora, "exp": ahora + _EXPIRACION_SEGUNDOS}
    return jwt.encode(payload, SESSION_SECRET_KEY, algorithm=_ALGORITMO)


def _generar_user_id() -> str:
    """Nombre corto y amigable (ej. 'Valentina482'), no un hex ilegible —
    se muestra en el front y es literalmente el valor que viaja en
    {user_id, pregunta} del contrato de la API. Faker genera esto de forma
    local, sin llamadas de red ni telemetría — no es un dato personal real,
    es un nombre de fantasía generado al azar. El sufijo numérico (4 dígitos,
    aleatorio criptográfico) da suficiente espacio para evitar colisiones
    entre sesiones distintas incluso con volumen alto — dos personas nunca
    deberían terminar compartiendo el mismo user_id, o sus memorias de
    conversación se mezclarían.

    Se quitan tildes/ñ (ej. "Úrsula" -> "Ursula") para evitar inconsistencias
    si el user_id se normaliza distinto en algún punto del camino (front,
    URL, comparación de texto) — más seguro como identificador técnico."""
    nombre = _fake.first_name()
    nombre_sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", nombre) if not unicodedata.combining(c)
    )
    sufijo = secrets.randbelow(9000) + 1000  # 1000-9999
    return f"{nombre_sin_tildes}{sufijo}"


def crear_sesion() -> tuple[str, str]:
    """Genera un user_id aleatorio y amigable (SIN ningún dato personal
    real) y lo firma en un JWT. Devuelve (user_id, token)."""
    user_id = _generar_user_id()
    return user_id, _firmar(user_id)


def verificar_sesion(token: str) -> str:
    """Verifica la firma del token y devuelve el session_id real. Lanza
    TokenInvalidoError si algo no calza — este es el punto donde se
    rechaza cualquier intento de usar un user_id falsificado o adivinado."""
    try:
        payload = jwt.decode(token, SESSION_SECRET_KEY, algorithms=[_ALGORITMO])
        return payload["sid"]
    except jwt.PyJWTError as e:
        raise TokenInvalidoError(f"Token inválido o expirado: {e!r}") from e