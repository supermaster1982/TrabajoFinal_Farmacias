"""
tool_rag.py — Tool de búsqueda del vademécum. La lógica de retrieve/rerank/
filter ahora vive en rag_subgrafo.py, como un StateGraph propio — esta tool
solo lo invoca y formatea el resultado para el agente.
"""

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from asistente_farmacias.tools.rag_subgrafo import invocar_subgrafo


@tool
def buscar_ficha_medicamento(medicamento: str, config: RunnableConfig = None) -> str:
    """Busca información general de un medicamento en el vademécum (ficha técnica):
    clase, indicaciones, forma de dosificación de referencia, mecanismo de acción,
    efectos secundarios. Usa esta herramienta cuando el usuario pregunte qué es un
    medicamento, para qué sirve, o pida información general sobre él — NUNCA para
    decidir una dosis para una persona ni indicar tratamiento."""
    try:
        filtradas = invocar_subgrafo(medicamento, config=config)
    except Exception as e:
        return f"No pude consultar el vademécum en este momento ({e!r})."

    if not filtradas:
        return (
            f"No encontré información suficientemente relevante sobre "
            f"'{medicamento}' en el vademécum indexado."
        )

    bloques = []
    for ficha, score in filtradas:
        bloques.append(
            f"[Fuente: {ficha.metadata.get('fuente', 'vademécum')} — "
            f"{ficha.metadata.get('drug_name', '?')} · relevancia={score:.2f}]\n"
            f"{ficha.page_content}"
        )
    return "\n\n".join(bloques)