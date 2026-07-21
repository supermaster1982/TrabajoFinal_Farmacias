"""
tool_minsal.py — Consultas en vivo a la API pública de MINSAL (farmacias).

Expone DOS tools, sobre DOS endpoints distintos, para que el agente elija
según la intención de la pregunta (routing por LLM, no por código):

  - consultar_farmacias_de_turno       -> getLocalesTurnos.php  (¿qué está ABIERTA ahora?)
  - consultar_farmacias_registradas    -> getLocales.php        (directorio completo, esté o no de turno)

Schemas reales confirmados manualmente el 2026-07-20 (pegando un registro de
ejemplo desde el navegador — el sitio bloquea fetch automático tipo bot):

getLocalesTurnos.php (fecha en formato YYYY-MM-DD):
{
  "fecha": "2026-07-20", "local_id": "20", "fk_region": "6", "fk_comuna": "59", "fk_localidad": "17",
  "local_nombre": "SALCOBRAND", "comuna_nombre": "LIMACHE", "localidad_nombre": "LIMACHE",
  "local_direccion": "URMENETA 68", "funcionamiento_hora_apertura": "09:00:00",
  "funcionamiento_hora_cierre": "23:00:00", "local_telefono": "+5624223300 anexo 5300",
  "local_lat": "-32.98...", "local_lng": "-71.27...", "funcionamiento_dia": "lunes"
}

getLocales.php (¡MISMO esquema, pero "fecha" en formato DD-MM-YY, distinto!):
{
  "fecha": "20-07-26", "local_id": "3", "local_nombre": "CRUZ VERDE", "comuna_nombre": "LIMACHE",
  "localidad_nombre": "LIMACHE", "local_direccion": "URMENETA 99",
  "funcionamiento_hora_apertura": "08:30:00", "funcionamiento_hora_cierre": "18:30:00",
  "local_telefono": "+56332415940", "local_lat": "...", "local_lng": "...",
  "funcionamiento_dia": "lunes", "fk_region": "6", "fk_comuna": "59", "fk_localidad": "17"
}
"""

import unicodedata

import requests
from langchain_core.tools import tool

URL_TURNOS = "https://midas.minsal.cl/farmacia_v2/WS/getLocalesTurnos.php"
URL_LOCALES = "https://midas.minsal.cl/farmacia_v2/WS/getLocales.php"
TIMEOUT_SEGUNDOS = 5


def _sin_tildes_mayus(texto: str) -> str:
    """Normaliza para comparar comunas sin depender de tildes/mayúsculas
    (la API devuelve comuna_nombre en MAYÚSCULAS y sin tildes)."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.strip().upper()


def _es_turno_nocturno(apertura: str, cierre: str) -> bool:
    """True si el horario cruza medianoche (cierre < apertura numéricamente)."""
    return cierre < apertura


def _consultar_api_minsal(url: str) -> tuple[list | None, str | None]:
    """Hace el GET con timeout y devuelve (registros, None) o (None, mensaje_error).
    Centraliza el manejo de errores para no repetirlo en cada tool."""
    try:
        respuesta = requests.get(url, timeout=TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
        registros = respuesta.json()
    except requests.exceptions.Timeout:
        return None, "No pude consultar la API de MINSAL a tiempo (se demoró demasiado)."
    except requests.exceptions.RequestException:
        return None, "La API de MINSAL no está respondiendo en este momento."
    except ValueError:
        return None, "La API de MINSAL devolvió una respuesta inesperada (no era JSON válido)."

    if not isinstance(registros, list):
        return None, "La API de MINSAL devolvió un formato inesperado."
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
    if error:
        return error

    coincidencias = _filtrar_por_comuna(registros, comuna)
    if not coincidencias:
        return (
            f"No encontré farmacias de turno registradas en '{comuna}' en este momento, "
            f"según la API de MINSAL. Puede que no haya ninguna de turno ahora mismo, "
            f"o que el nombre de la comuna esté escrito distinto a como lo registra MINSAL."
        )

    lineas = [_formatear_local(r) for r in coincidencias]
    fecha = coincidencias[0].get("fecha", "fecha no informada")
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
    if error:
        return error

    coincidencias = _filtrar_por_comuna(registros, comuna)
    if not coincidencias:
        return f"No encontré farmacias registradas en '{comuna}' según el directorio de MINSAL."

    lineas = [_formatear_local(r) for r in coincidencias]
    return (
        f"Farmacias registradas en {comuna} (directorio MINSAL, no todas están de turno ahora):\n"
        + "\n".join(lineas)
    )
