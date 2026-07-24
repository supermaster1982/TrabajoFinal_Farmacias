"""
tool_rag.py — Búsqueda semántica sobre el vademécum indexado en Qdrant Cloud.

La colección debe estar poblada primero (correr load_vademecum.py una vez).
Esta tool SOLO consulta, nunca modifica el índice.

Idioma: el índice está en inglés (dataset original). Esta tool devuelve la
ficha en inglés, con su cita; la traducción al español la hace el LLM
principal al redactar la respuesta final (no se traduce acá, para no
duplicar ese trabajo ni arriesgar inconsistencias entre tool y respuesta).

IMPORTANTE (guardrail, ver graph.py/basic.py): esta tool devuelve información
de referencia de la ficha (incluyendo el campo "Strength", ej. "325 mg"),
pero eso es un dato descriptivo del medicamento, NO una recomendación de
dosis para una persona específica. La tool no decide cómo se usa ese dato —
esa distinción la aplica el guardrail sobre la respuesta final.
"""

import os

from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIMS = 256
COLLECTION = "vademecum_medicamentos"
TOP_K = 3

_vector_store = None


def _get_vector_store() -> QdrantVectorStore:
    """Conexión perezosa (lazy) a Qdrant: solo se crea la primera vez que se
    llama a la tool, no al importar el módulo. Esto evita que el servidor
    falle al arrancar si por algún motivo Qdrant no está disponible en ese
    instante — el error solo ocurre si alguien de verdad pregunta algo de
    medicamentos, no al iniciar la app."""
    global _vector_store
    if _vector_store is None:
        client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
        embeddings = OpenAIEmbeddings(model=EMBED_MODEL, dimensions=EMBED_DIMS)
        _vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION, embedding=embeddings)
    return _vector_store


@tool
def buscar_ficha_medicamento(medicamento: str) -> str:
    """Busca información general de un medicamento en el vademécum (ficha técnica):
    clase, indicaciones, forma de dosificación de referencia, mecanismo de acción,
    efectos secundarios. Usa esta herramienta cuando el usuario pregunte qué es un
    medicamento, para qué sirve, o pida información general sobre él — NUNCA para
    decidir una dosis para una persona ni indicar tratamiento."""
    try:
        vector_store = _get_vector_store()
        resultados = vector_store.similarity_search(medicamento, k=TOP_K)
    except Exception as e:
        return f"No pude consultar el vademécum en este momento ({e!r})."

    if not resultados:
        return f"No encontré información sobre '{medicamento}' en el vademécum indexado."

    fichas = []
    for r in resultados:
        fichas.append(
            f"[Fuente: {r.metadata.get('fuente', 'vademécum')} — "
            f"{r.metadata.get('drug_name', '?')}]\n{r.page_content}"
        )
    return "\n\n".join(fichas)