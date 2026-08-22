"""
load_vademecum_chile.py — Script de carga independiente para el vademécum
chileno (JSON compartido por el profesor). Se corre UNA VEZ (o cuando cambie
el JSON) para poblar una colección NUEVA de Qdrant, separada del vademécum
de Kaggle — ambas coexisten, ninguna reemplaza a la otra.

Uso:
    poetry run python load_vademecum_chile.py

Requiere en el .env: OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY

Fuente: vademecum.json (provisto por el profesor como material de clase).
No se sube al repositorio público — ver data/vademecum_chile/.gitignore.

Estrategia de chunking: 1 medicamento = 1 chunk (todas sus secciones juntas),
mismo criterio que load_vademecum.py con el CSV de Kaggle — las preguntas
reales del asistente son sobre un medicamento completo ("¿para qué sirve
X?"), no sobre una sección aislada. Con 1 sección = 1 chunk, el mismo
dataset generaría ~7-9x más vectores (mayor costo y tiempo de indexado) sin
beneficio real para este caso de uso.

Hallazgo real de calidad de datos: los nombres de "seccion" del JSON
original vienen con basura pegada al final en muchos registros — el nombre
del principio activo del SIGUIENTE medicamento, sin espacio de separación
(ej. "Advertencias y precaucionesÁcaros de polvo doméstico" en vez de
"Advertencias y precauciones"). Se corrigió normalizando cada nombre de
sección al prefijo más largo que coincide con la lista de 13 secciones
reales conocidas — ver _normalizar_seccion().
"""

import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore

load_dotenv()

# ============================================================================
# CONSTANTES — mismo modelo/dimensión que el vademécum de Kaggle, para que
# ambas colecciones sean comparables si en algún momento se busca en las dos.
# ============================================================================
EMBED_MODEL = "text-embedding-3-large"
EMBED_DIMS = 256
COLLECTION = "vademecum_chile"  # colección NUEVA — no toca "vademecum_medicamentos" (Kaggle)
JSON_PATH = Path(__file__).parent / "data" / "vademecum_chile" / "vademecum.json"

assert os.getenv("OPENAI_API_KEY"), "Falta OPENAI_API_KEY en .env"
assert os.getenv("QDRANT_URL"), "Falta QDRANT_URL en .env"
assert os.getenv("QDRANT_API_KEY"), "Falta QDRANT_API_KEY en .env"

# Las 13 secciones reales conocidas del vademécum (ver docstring: hallazgo de
# calidad de datos). Ordenadas de más larga a más corta para que, al buscar
# el prefijo más largo que coincide, "Efectos sobre la capacidad de conducir"
# no quede cortada prematuramente por una sección más corta que también
# empareje como prefijo.
_SECCIONES_CONOCIDAS = sorted(
    [
        "Advertencias y precauciones",
        "Contraindicaciones",
        "Efectos sobre la capacidad de conducir",
        "Embarazo",
        "Indicaciones terapéuticas",
        "Insuficiencia hepática",
        "Insuficiencia renal",
        "Interacciones",
        "Lactancia",
        "Mecanismo de acción",
        "Modo de administración",
        "Reacciones adversas",
        "Sobredosificación",
    ],
    key=len,
    reverse=True,
)


def _normalizar_seccion(seccion_cruda: str) -> str:
    """Corrige el bug de scraping: corta cualquier basura pegada después del
    nombre real de la sección. Si no coincide con ninguna sección conocida,
    devuelve el texto tal cual (mejor mostrar algo raro que perder datos)."""
    for candidata in _SECCIONES_CONOCIDAS:
        if seccion_cruda.startswith(candidata):
            return candidata
    return seccion_cruda.strip()


def _limpiar_html(texto: str) -> str:
    """El campo 'contenido' trae tags HTML sueltos (ej. <sub>H1<\\sub>,
    residuo del scraping original) — se remueven para no ensuciar el texto
    que se embebe ni lo que eventualmente se le muestra al usuario."""
    return re.sub(r"<[^>]+>", "", texto).strip()


# ============================================================================
# CARGA: 1 medicamento = 1 Document (ver justificación de chunking arriba)
# ============================================================================
def cargar_documentos(limite: int | None = None) -> list[Document]:
    if not JSON_PATH.exists():
        raise FileNotFoundError(
            f"No encontré el JSON en {JSON_PATH}. Es material de clase "
            f"(no se distribuye en el repo) — pide el archivo y colócalo "
            f"en esa ruta exacta."
        )

    with open(JSON_PATH, encoding="utf-8") as f:
        medicamentos = json.load(f)

    if limite:
        medicamentos = medicamentos[:limite]

    documentos = []
    for med in medicamentos:
        nombre = med.get("nombre", "").strip()
        if not nombre:
            continue  # sin nombre, no hay forma de que una búsqueda lo encuentre

        secciones_texto = []
        for info in med.get("informacion", []):
            seccion = _normalizar_seccion(info.get("seccion", ""))
            contenido = _limpiar_html(info.get("contenido", ""))
            if contenido:
                secciones_texto.append(f"{seccion}: {contenido}")

        texto = (
            f"Nombre: {nombre}. "
            f"Principio activo (ATC): {med.get('atc', 'no informado')}. "
            f"País: {med.get('pais', 'no informado')}. "
            f"Laboratorio: {med.get('laboratorio', 'no informado')}. "
            f"Vía de administración: {med.get('via', 'no informada')}. "
            f"Forma farmacéutica: {med.get('forma', 'no informada')}. "
            + " ".join(secciones_texto)
        )

        documentos.append(
            Document(
                page_content=texto,
                metadata={
                    "fuente": "Vademécum Chile (material de clase)",
                    "nombre": nombre,
                    "atc": med.get("atc", ""),
                    "laboratorio": med.get("laboratorio", ""),
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

    # 12,411 documentos de una sola vez puede ser mucho para un solo batch de
    # la API de embeddings — se sube en lotes para evitar timeouts/errores
    # de tamaño de payload.
    TAMANO_LOTE = 200
    total = len(documentos)
    for i in range(0, total, TAMANO_LOTE):
        lote = documentos[i : i + TAMANO_LOTE]
        vector_store.add_documents(lote)
        print(f"  {min(i + TAMANO_LOTE, total)}/{total} documentos indexados...")

    info = client.get_collection(COLLECTION)
    print(f"\n✅ Índice listo · {info.points_count} vectores en Qdrant/{COLLECTION} "
          f"(COSINE, {EMBED_DIMS}d)")


# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    # Uso: poetry run python load_vademecum_chile.py           -> indexa TODO (12,411)
    #      poetry run python load_vademecum_chile.py 50        -> indexa solo los primeros 50
    #                                                              (para probar antes de gastar
    #                                                              tiempo/costo en el dataset completo)
    limite = None
    if len(sys.argv) > 1:
        limite = int(sys.argv[1])
        print(f"⚠️  Modo muestra: se indexarán solo los primeros {limite} medicamentos.\n")

    print(f"Cargando documentos desde: {JSON_PATH}\n")
    documentos = cargar_documentos(limite=limite)
    print(f"Total documentos cargados: {len(documentos)} (1 medicamento = 1 chunk, sin splitting)\n")
    indexar(documentos)