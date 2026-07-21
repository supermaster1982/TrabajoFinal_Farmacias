"""
tool_rag.py — STUB (stage 0).

Esta tool todavía NO consulta Qdrant. Devuelve una ficha fija, marcada como
simulada, solo para validar el routing del agente (RAG vs. MINSAL) y el
formato de respuesta con cita de fuente.

TODO (rama feature/rag-vademecum):
  - Cargar y trocear el dataset "Comprehensive Drug Information" (Kaggle).
  - Indexar en Qdrant Cloud (embeddings OpenAI, colección propia).
  - similarity_search real + devolver el/los chunk(s) con su fuente para citar.
  - Definir estrategia de idioma: indexar en inglés, traducir solo la
    respuesta final (decisión ya tomada — ver conversación).
  - Nunca debe convertirse en recomendación de dosis: la tool solo entrega
    información de la ficha, el guardrail decide qué se puede decir con eso.
"""

from langchain_core.tools import tool


@tool
def buscar_ficha_medicamento(medicamento: str) -> str:
    """Busca información general de un medicamento en el vademécum (ficha técnica).
    Usa esta herramienta cuando el usuario pregunte qué es un medicamento, para
    qué sirve, o pida información general sobre él — NUNCA para decidir dosis
    ni indicar tratamiento."""
    return (
        f"[FICHA SIMULADA — STUB, no es el vademécum real]\n"
        f"Medicamento consultado: {medicamento}\n"
        f"Categoría: analgésico/antiinflamatorio (ejemplo)\n"
        f"Descripción general: información de referencia de ejemplo, sin datos "
        f"clínicos reales.\n"
        f"Fuente: dataset de ejemplo — la ficha real vendrá del vademécum "
        f"indexado en Qdrant en la siguiente etapa."
    )
