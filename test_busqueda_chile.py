"""
test_busqueda_chile.py — Script TEMPORAL, para confirmar manualmente que el
SUBGRAFO completo (retrieve -> filtro 0.55 -> resultado final) funciona
bien sobre la colección vademecum_chile — a diferencia de la primera
versión de este script, que llamaba a Qdrant directo sin ningún filtro
(por eso "Abatero" salía sin descartarse). No es parte del sistema —
bórralo cuando termines de validar.

Uso:
    poetry run python test_busqueda_chile.py

Requiere haber corrido antes: poetry run python load_vademecum_chile.py [N]
"""

import sys
from pathlib import Path
from dotenv import load_dotenv
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langgraph")

load_dotenv()               

# Mismo patrón que eval_langsmith.py: el paquete real vive en src/.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from asistente_farmacias.tools.rag_subgrafo_chile import invocar_subgrafo_chile  # noqa: E402

PREGUNTAS_DE_PRUEBA = [
    "Aartfenacin",  # búsqueda por nombre de fantasía exacto
    "para qué sirve la fexofenadina",  # búsqueda por principio activo, formulada como pregunta
    "medicamento para infecciones urinarias con ciprofloxacino",  # pregunta funcional
]

for pregunta in PREGUNTAS_DE_PRUEBA:
    print(f"\n{'='*70}\nPREGUNTA: {pregunta}\n{'='*70}")
    filtradas = invocar_subgrafo_chile(pregunta)
    if not filtradas:
        print("  (sin resultados — ninguna candidata superó el umbral 0.55)")
        continue
    for ficha, score in filtradas:
        nombre = ficha.metadata.get("nombre", "?")
        print(f"  score={score:.3f} · {nombre}")