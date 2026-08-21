"""
tool_rag_chile.py — Tool de búsqueda del vademécum CHILENO (material de
clase, provisto por el profesor). Mismo patrón que tool_rag.py: esta tool
solo invoca el subgrafo y formatea el resultado — la búsqueda real
(retrieve/rerank/filter, umbral 0.54) vive en rag_subgrafo_chile.py.

Rol en el sistema: fuente SECUNDARIA. El agente la usa solo si
'buscar_ficha_medicamento' (vademécum de Kaggle, ya evaluado y probado)
no encontró información suficientemente relevante — mismo patrón de
fallback que ya existe entre 'consultar_farmacias_de_turno' y
'consultar_farmacias_registradas' en tool_minsal.py. Esto evita cualquier
regresión sobre las 20 preguntas del dataset formal (todas encuentran
resultado en Kaggle, así que nunca llegan a necesitar esta tool) y cubre
justo el caso que causó el hallazgo de Viadil: un medicamento chileno
ausente del corpus internacional.
"""

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from asistente_farmacias.tools.rag_subgrafo_chile import invocar_subgrafo_chile


@tool
def buscar_ficha_medicamento_chile(medicamento: str, config: RunnableConfig = None) -> str:
    """Busca información general de un medicamento en el vademécum CHILENO
    (marcas y genéricos registrados en Chile: mecanismo de acción, modo de
    administración, contraindicaciones, efectos adversos). Úsala SOLO si
    'buscar_ficha_medicamento' (vademécum internacional) ya respondió que no
    encontró información suficientemente relevante sobre ese medicamento —
    es la segunda fuente, no la primera. NUNCA para decidir una dosis para
    una persona ni indicar tratamiento."""
    try:
        filtradas = invocar_subgrafo_chile(medicamento, config=config)
    except Exception as e:
        return f"No pude consultar el vademécum chileno en este momento ({e!r})."

    if not filtradas:
        return (
            f"No encontré información suficientemente relevante sobre "
            f"'{medicamento}' tampoco en el vademécum chileno indexado."
        )

    bloques = []
    for ficha, score in filtradas:
        bloques.append(
            f"[Fuente: {ficha.metadata.get('fuente', 'vademécum chileno')} — "
            f"{ficha.metadata.get('nombre', '?')} · relevancia={score:.2f}]\n"
            f"{ficha.page_content}"
        )
    return "\n\n".join(bloques)