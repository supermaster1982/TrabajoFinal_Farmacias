"""
tool_minsal.py — Consultas en vivo a la API pública de MINSAL (farmacias).

Expone DOS tools, sobre DOS endpoints distintos, para que el agente elija
según la intención de la pregunta (routing por LLM, no por código):

  - consultar_farmacias_de_turno       -> getLocalesTurnos.php  (¿qué está ABIERTA ahora?)
  - consultar_farmacias_registradas    -> getLocales.php        (directorio completo, esté o no de turno)

CACHÉ (nuevo): el enunciado del trabajo pide explícitamente "timeout, cache
corto y fallback rotulado" — ya teníamos el timeout, faltaba el caché. Se
cachea la respuesta CRUDA de cada endpoint (no por comuna — la API devuelve
TODAS las comunas en cada llamada, así que cachear por endpoint es el punto
natural) por 15 minutos, igual al ejemplo del enunciado ("cache 15 min").
Esto evita golpear la API real en cada pregunta — importante tanto para no
abusar de un servicio público gratuito, como para la latencia percibida
por el usuario (una consulta repetida en la ventana de 15 min responde
casi instantáneo, sin esperar la llamada HTTP real).
"""

import time
import unicodedata
import json
from pathlib import Path

import requests
from langchain_core.tools import tool

#URL_TURNOS = "https://midas.minsal.cl/farmacia_v2/WS/getLocalesTurnos.php"
#URL_LOCALES = "https://midas.minsal.cl/farmacia_v2/WS/getLocales.php"
URL_TURNOS = "https://minsal-proxy.alexis-contrerasnaranjo.workers.dev/turnos"
URL_LOCALES = "https://minsal-proxy.alexis-contrerasnaranjo.workers.dev/locales"

TIMEOUT_SEGUNDOS = 5
CACHE_TTL_SEGUNDOS = 15 * 60  # 15 minutos, mismo valor que el ejemplo del enunciado

# Caché en memoria del proceso: {url: (timestamp_guardado, registros)}
# Se pierde al reiniciar el servidor — aceptable para este proyecto (mismo
# criterio que la memoria conversacional, que también vive en RAM).
_cache: dict[str, tuple[float, list]] = {}
# Fallback de último recurso: snapshot estático, generado con
# generar_snapshot_minsal.py, para cuando la API en vivo falla de forma
# sostenida (confirmado con evidencia real: Cloudflare bloquea con 403 las
# IP de datacenter extranjeras usadas por el hosting — ver docs/). Permitido
# explícitamente por el enunciado: "snapshot documentado con fecha visible".
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_SNAPSHOTS = {
    URL_TURNOS: _DATA_DIR / "snapshot_minsal_turnos.json",
    URL_LOCALES: _DATA_DIR / "snapshot_minsal_locales.json",
}


def _cargar_snapshot(url: str) -> tuple[list | None, str | None]:
    """Devuelve (registros, fecha_captura) del snapshot, o (None, None) si
    no existe o no se puede leer. Se usa SOLO cuando la llamada en vivo ya
    falló — nunca reemplaza el intento real."""
    path = _SNAPSHOTS.get(url)
    if not path or not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text())
        return data["registros"], data["capturado_en"]
    except Exception:
        return None, None


def _sin_tildes_mayus(texto: str) -> str:
    """Normaliza para comparar comunas sin depender de tildes/mayúsculas
    (la API devuelve comuna_nombre en MAYÚSCULAS y sin tildes)."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.strip().upper()


def _es_turno_nocturno(apertura: str, cierre: str) -> bool:
    """True si el horario cruza medianoche (cierre < apertura numéricamente)."""
    return cierre < apertura


def _consultar_api_minsal(url: str) -> tuple[list | None, str | None]:
    """Hace el GET con timeout, usando caché de 15 min. Devuelve
    (registros, None) para dato en vivo/caché, (registros, "__SNAPSHOT__<fecha>")
    si cayó al snapshot de emergencia, o (None, mensaje_error) si ni la
    llamada en vivo ni el snapshot funcionaron."""
    ahora = time.time()

    if url in _cache:
        guardado_en, registros_cacheados = _cache[url]
        if ahora - guardado_en < CACHE_TTL_SEGUNDOS:
            return registros_cacheados, None
        # Expiró: se saca del caché y sigue al fetch real más abajo.
        del _cache[url]

    def _fallback_o_error(mensaje_error: str) -> tuple[list | None, str | None]:
        registros_snap, fecha_snap = _cargar_snapshot(url)
        if registros_snap:
            return registros_snap, f"__SNAPSHOT__{fecha_snap}"
        return None, mensaje_error

    try:
        respuesta = requests.get(url, timeout=TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
        registros = respuesta.json()
    except requests.exceptions.Timeout:
        return _fallback_o_error("No pude consultar la API de MINSAL a tiempo (se demoró demasiado).")
    except requests.exceptions.RequestException:
        return _fallback_o_error("La API de MINSAL no está respondiendo en este momento.")
    except ValueError:
        return _fallback_o_error("La API de MINSAL devolvió una respuesta inesperada (no era JSON válido).")

    if not isinstance(registros, list):
        return _fallback_o_error("La API de MINSAL devolvió un formato inesperado.")

    _cache[url] = (ahora, registros)
    return registros, None


def _filtrar_por_comuna(registros: list, comuna: str) -> list:
    comuna_normalizada = _sin_tildes_mayus(comuna)
    return [r for r in registros if _sin_tildes_mayus(r.get("comuna_nombre", "")) == comuna_normalizada]


def _formatear_local(r: dict) -> str:
    apertura = r.get("funcionamiento_hora_apertura", "?")
    cierre = r.get("funcionamiento_hora_cierre", "?")
    nota_nocturno = ""
    if apertura != "?" and cierre != "?" and _es_turno_nocturno(apertura, cierre):
        nota_nocturno = " (cierra al día siguiente)"
    return (
        f"- {r.get('local_nombre', '(sin nombre)')} — {r.get('local_direccion', '(sin dirección)')}, "
        f"{r.get('comuna_nombre', '')}. Horario: {apertura} a {cierre}{nota_nocturno}. "
        f"Tel: {r.get('local_telefono', 'no informado')}."
    )


@tool
def consultar_farmacias_de_turno(comuna: str) -> str:
    """Busca farmacias de turno (ABIERTAS AHORA MISMO) en una comuna de Chile,
    consultando en vivo la API de MINSAL. Usa esta herramienta cuando el
    usuario pregunte por farmacias abiertas, de turno, o dónde comprar un
    medicamento ahora mismo."""
    registros, error = _consultar_api_minsal(URL_TURNOS)

    es_snapshot = error and error.startswith("__SNAPSHOT__")
    if error and not es_snapshot:
        return error
    if not registros:
        return error or f"No pude obtener datos de farmacias de turno en '{comuna}'."

    coincidencias = _filtrar_por_comuna(registros, comuna)
    if not coincidencias:
        return (
            f"No encontré farmacias de turno registradas en '{comuna}' en este momento, "
            f"según la API de MINSAL. Puede que no haya ninguna de turno ahora mismo, "
            f"o que el nombre de la comuna esté escrito distinto a como lo registra MINSAL."
        )

    lineas = [_formatear_local(r) for r in coincidencias]
    fecha = coincidencias[0].get("fecha", "fecha no informada")

    if es_snapshot:
        fecha_captura = error.replace("__SNAPSHOT__", "")
        return (
            f"⚠️ No pude conectar en vivo con MINSAL — mostrando un snapshot guardado "
            f"del {fecha_captura} (puede estar desactualizado):\n" + "\n".join(lineas)
        )

    return f"Farmacias de turno en {comuna} (dato en vivo de MINSAL, {fecha}):\n" + "\n".join(lineas)


@tool
def consultar_farmacias_registradas(comuna: str) -> str:
    """Busca TODAS las farmacias registradas por MINSAL en una comuna de Chile
    (estén o no de turno ahora mismo) — es el directorio completo, no solo las
    abiertas. Usa esta herramienta cuando el usuario pregunte si existe una
    farmacia en particular, o quiera un listado general de farmacias en una
    comuna. NO uses esta tool si preguntan cuál está ABIERTA/DE TURNO ahora —
    para eso usa consultar_farmacias_de_turno."""
    registros, error = _consultar_api_minsal(URL_LOCALES)

    es_snapshot = error and error.startswith("__SNAPSHOT__")
    if error and not es_snapshot:
        return error
    if not registros:
        return error or f"No pude obtener el directorio de farmacias en '{comuna}'."

    coincidencias = _filtrar_por_comuna(registros, comuna)
    if not coincidencias:
        return f"No encontré farmacias registradas en '{comuna}' según el directorio de MINSAL."

    lineas = [_formatear_local(r) for r in coincidencias]

    if es_snapshot:
        fecha_captura = error.replace("__SNAPSHOT__", "")
        return (
            f"⚠️ No pude conectar en vivo con MINSAL — mostrando un snapshot guardado "
            f"del {fecha_captura} (puede estar desactualizado):\n" + "\n".join(lineas)
        )

    return (
        f"Farmacias registradas en {comuna} (directorio MINSAL, no todas están de turno ahora):\n"
        + "\n".join(lineas)
    )
