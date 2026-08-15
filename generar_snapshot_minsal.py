"""
generar_snapshot_minsal.py — Captura un snapshot estático de la API de MINSAL,
para usar como fallback si el hosting queda bloqueado por Cloudflare (confirmado
con evidencia real: 403 desde IP de datacenter extranjera, agosto 2026).

Uso: poetry run python generar_snapshot_minsal.py
Regenerar cerca de la demo para "turnos" (cambia a diario); "locales" es
estable y no hace falta regenerarlo tan seguido.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ENDPOINTS = {
    "turnos": "https://midas.minsal.cl/farmacia_v2/WS/getLocalesTurnos.php",
    "locales": "https://midas.minsal.cl/farmacia_v2/WS/getLocales.php",
}

DEST = Path(__file__).parent / "data"
DEST.mkdir(exist_ok=True)


def main():
    capturado_en = datetime.now(timezone.utc).isoformat()
    for nombre, url in ENDPOINTS.items():
        print(f"Descargando {nombre}...")
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        registros = r.json()
        destino = DEST / f"snapshot_minsal_{nombre}.json"
        destino.write_text(json.dumps({"capturado_en": capturado_en, "registros": registros}, ensure_ascii=False, indent=2))
        print(f"  {len(registros)} registros guardados en {destino}")
    print(f"\nSnapshot capturado: {capturado_en}")


if __name__ == "__main__":
    main()