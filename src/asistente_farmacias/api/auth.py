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
import time
import uuid

import jwt

SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY")
if not SESSION_SECRET_KEY:
    raise RuntimeError(
        "Falta SESSION_SECRET_KEY en tu .env. Genera una con:\n"
        "  python3 -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "y agrégala a tu .env como SESSION_SECRET_KEY=<lo que imprima>"
    )

_ALGORITMO = "HS256"
_EXPIRACION_SEGUNDOS = 45 * 60  # 45 min — se renueva automáticamente en cada
# pregunta mientras la persona esté activa (ver renovar_sesion). Si alguien
# roba un token y no lo usa de inmediato, deja de servir pronto.


class TokenInvalidoError(Exception):
    """El token no existe, está mal formado, expiró, o la firma no coincide
    con nuestra SESSION_SECRET_KEY (alguien intentó falsificarlo)."""


def _firmar(session_id: str) -> str:
    ahora = int(time.time())
    payload = {"sid": session_id, "iat": ahora, "exp": ahora + _EXPIRACION_SEGUNDOS}
    return jwt.encode(payload, SESSION_SECRET_KEY, algorithm=_ALGORITMO)


def crear_sesion() -> tuple[str, str]:
    """Genera un session_id aleatorio (SIN ningún dato personal) y lo firma
    en un JWT. Devuelve (session_id, token)."""
    session_id = str(uuid.uuid4())
    return session_id, _firmar(session_id)


def renovar_sesion(session_id: str) -> str:
    """Emite un token NUEVO para el mismo session_id, con la expiración
    reiniciada a 45 min desde ahora. Se llama en cada pregunta exitosa —
    así, mientras la persona siga activa, la sesión nunca expira de
    verdad; si deja de usarse (token robado y no reutilizado, o la
    persona simplemente se va), expira en 45 min como máximo."""
    return _firmar(session_id)


def verificar_sesion(token: str) -> str:
    """Verifica la firma del token y devuelve el session_id real. Lanza
    TokenInvalidoError si algo no calza — este es el punto donde se
    rechaza cualquier intento de usar un user_id falsificado o adivinado."""
    try:
        payload = jwt.decode(token, SESSION_SECRET_KEY, algorithms=[_ALGORITMO])
        return payload["sid"]
    except jwt.PyJWTError as e:
        raise TokenInvalidoError(f"Token inválido o expirado: {e!r}") from e