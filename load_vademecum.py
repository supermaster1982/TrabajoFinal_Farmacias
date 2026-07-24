"""
load_vademecum.py — Script de carga independiente para el vademécum (RAG).

Se corre UNA VEZ (o cuando cambie el CSV) para poblar la colección de Qdrant.
El servidor (agent/tools/tool_rag.py) solo CONSULTA esa colección, nunca la
modifica.

Uso:
    poetry run python load_vademecum.py

Requiere en el .env: OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY

Dataset: "Comprehensive Drug Information" (Kaggle) — CSV en inglés, columnas:
Drug ID, Drug Name, Generic Name, Drug Class, Indications, Dosage Form,
Strength, Route of Administration, Mechanism of Action, Side Effects.

Estrategia de chunking: NO se trocea nada. Cada fila del CSV es una unidad
semántica completa y ya acotada (una ficha de medicamento) — a diferencia de
un documento largo, partirla arriesgaría separar el nombre del medicamento
de sus efectos secundarios o indicaciones en chunks distintos. 1 fila = 1
chunk = 1 Document.

Estrategia de idioma: se indexa en INGLÉS (el idioma original del dataset).
La traducción al español ocurre solo en la respuesta final del LLM, no en
el índice — así evitamos que un error de traducción quede "enterrado" en el
vector store y se repita en cada respuesta (decisión ya discutida y
documentada en el proyecto).
"""

import csv
import os
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore

load_dotenv()

# ============================================================================
# CONSTANTES
# ============================================================================
EMBED_MODEL = "text-embedding-3-large"
EMBED_DIMS = 256
COLLECTION = "vademecum_medicamentos"
CSV_PATH = Path(__file__).parent / "data" / "vademecum" / "DrugData-selected-columns.csv"

assert os.getenv("OPENAI_API_KEY"), "Falta OPENAI_API_KEY en .env"
assert os.getenv("QDRANT_URL"), "Falta QDRANT_URL en .env"
assert os.getenv("QDRANT_API_KEY"), "Falta QDRANT_API_KEY en .env"


# ============================================================================
# CARGA: 1 fila del CSV = 1 Document (ver justificación de chunking arriba)
# ============================================================================
def cargar_documentos() -> list[Document]:
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"No encontré el CSV en {CSV_PATH}. Descárgalo de Kaggle "
            f"('Comprehensive Drug Information') y guárdalo con ese nombre "
            f"exacto en esa ruta."
        )

    documentos = []
    with open(CSV_PATH, encoding="utf-8") as f:
        lector = csv.DictReader(f, delimiter=";")
        for fila in lector:
            texto = (
                f"Drug ID: {fila['Drug ID']}. "
                f"Drug Name: {fila['Drug Name']}. "
                f"Generic Name: {fila['Generic Name']}. "
                f"Drug Class: {fila['Drug Class']}. "
                f"Indications: {fila['Indications']}. "
                f"Dosage Form: {fila['Dosage Form']}. "
                f"Strength: {fila['Strength']}. "
                f"Route of Administration: {fila['Route of Administration']}. "
                f"Mechanism of Action: {fila['Mechanism of Action']}. "
                f"Side Effects: {fila['Side Effects']}."
            )
            documentos.append(
                Document(
                    page_content=texto,
                    metadata={
                        "fuente": "Comprehensive Drug Information (Kaggle)",
                        "drug_id": fila["Drug ID"],
                        "drug_name": fila["Drug Name"],
                        "generic_name": fila["Generic Name"],
                        "drug_class": fila["Drug Class"],
                    },
                )
            )
    return documentos


# ============================================================================
# INDEXAR EN QDRANT CLOUD
# ============================================================================
def indexar(documentos: list[Document]) -> None:
    client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
    embeddings = OpenAIEmbeddings(model=EMBED_MODEL, dimensions=EMBED_DIMS)

    client.recreate_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=EMBED_DIMS, distance=Distance.COSINE),
    )

    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION, embedding=embeddings)
    vector_store.add_documents(documentos)

    info = client.get_collection(COLLECTION)
    print(f"\n✅ Índice listo · {info.points_count} vectores en Qdrant/{COLLECTION} "
          f"(COSINE, {EMBED_DIMS}d)")


# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    print(f"Cargando documentos desde: {CSV_PATH}\n")
    documentos = cargar_documentos()
    print(f"Total documentos cargados: {len(documentos)} (1 fila = 1 chunk, sin splitting)\n")
    indexar(documentos)