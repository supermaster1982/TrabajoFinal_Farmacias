"""
eval_vademecum.py — Mini-eval de calidad del RAG del vademécum.

Mismo patrón que la sección §6 (run_quality_experiment) de
Notebook_01_Ejercicio_Seguridad_Resultado.ipynb: un dataset fijo de
input/expected_output, un LLM-as-a-judge que puntúa correctness/
faithfulness/relevance (0 a 1), y una tabla comparativa entre DOS versiones
del pipeline — acá, específicamente:

  - "sin_rerank": retrieval simple (similarity_search top-3, sin puntuar).
  - "con_rerank": tu pipeline real (k=8 -> LLM puntúa -> filtro 0.4 -> top 3).

Objetivo: tener evidencia CUANTITATIVA (no solo intuición) de si el
re-rank + filter realmente mejora la calidad de las respuestas del
vademécum, para justificarlo en el informe.

Uso:
    poetry run python eval_vademecum.py

Requiere: OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY en .env (Qdrant ya
poblado con load_vademecum.py).
"""

import os
import time
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from pydantic import BaseModel, Field

load_dotenv(override=True)

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIMS = 256
COLLECTION = "vademecum_medicamentos"
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-5.4-mini")

# --- Dataset fijo de evaluación (mismo espíritu que QUALITY_DATASET del notebook) ---
# Preguntas sobre medicamentos que SÍ están en las 220 fichas del CSV.
QUALITY_DATASET = [
    {
        "pregunta": "¿Para qué sirve el Aspirin y qué efecto secundario tiene?",
        "esperado": "Es un analgésico usado para el dolor de cabeza; puede causar irritación estomacal.",
    },
    {
        "pregunta": "¿Qué tipo de medicamento es la Amoxicilina y para qué se usa?",
        "esperado": "Es un antibiótico usado para infecciones bacterianas.",
    },
    {
        "pregunta": "¿Cómo actúa el Lisinopril en el cuerpo?",
        "esperado": "Es un antihipertensivo que bloquea la conversión de angiotensina I a angiotensina II.",
    },
]


class PuntajeCalidad(BaseModel):
    correctness: float = Field(ge=0.0, le=1.0, description="Coincide con lo esperado.")
    faithfulness: float = Field(ge=0.0, le=1.0, description="Cada afirmación está respaldada por el contexto recuperado.")
    relevance: float = Field(ge=0.0, le=1.0, description="Responde directamente la pregunta.")
    razon: str = Field(..., description="Justificación breve.")


def _vector_store() -> QdrantVectorStore:
    client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
    embeddings = OpenAIEmbeddings(model=EMBED_MODEL, dimensions=EMBED_DIMS)
    return QdrantVectorStore(client=client, collection_name=COLLECTION, embedding=embeddings)


def _generar_respuesta(pregunta: str, fichas: list) -> str:
    """Redacta una respuesta simple en español a partir de las fichas — versión
    minimalista, solo para el eval (no pasa por el agente completo ni por
    los guardrails, ya que acá solo medimos la calidad del RETRIEVAL)."""
    contexto = "\n\n".join(f.page_content for f in fichas)
    llm = ChatOpenAI(model=JUDGE_MODEL, temperature=0)
    prompt = (
        "Responde la pregunta en español, usando solo la información del contexto. "
        "Si el contexto no alcanza, dilo.\n\n"
        f"Contexto:\n{contexto}\n\nPregunta: {pregunta}\n\nRespuesta:"
    )
    return llm.invoke(prompt).content


def _retrieval_sin_rerank(vs: QdrantVectorStore, pregunta: str) -> list:
    return vs.similarity_search(pregunta, k=3)


def _retrieval_con_rerank(vs: QdrantVectorStore, pregunta: str) -> list:
    """Reimplementa la lógica real de tool_rag.py (retrieval + LLM re-rank +
    filtro), para poder medirla aislada del resto del agente. Usa texto
    plano en vez de with_structured_output (ver nota en _juzgar)."""
    from langchain_openai import ChatOpenAI as _ChatOpenAI

    candidatas = vs.similarity_search(pregunta, k=8)
    llm = _ChatOpenAI(model=JUDGE_MODEL, temperature=0)

    prompt = (
        "Puntúa de 0.0 a 1.0 la relevancia de esta ficha para la pregunta. "
        "Responde SOLO con el número, nada más.\n\n"
        "Pregunta: {p}\n\nFicha: {f}"
    )

    puntuadas = []
    for ficha in candidatas:
        texto = llm.invoke(prompt.format(p=pregunta, f=ficha.page_content)).content
        try:
            score = float(texto.strip().split()[0])
        except (ValueError, IndexError):
            score = 0.5  # valor neutro si no se pudo parsear
        puntuadas.append((ficha, score))
    puntuadas.sort(key=lambda x: x[1], reverse=True)
    return [f for f, s in puntuadas if s >= 0.4][:3]


def _parsear_puntajes(texto: str) -> PuntajeCalidad:
    """Extrae los 3 scores + razón de una respuesta en texto plano, con
    formato 'clave: valor' por línea. Evita with_structured_output (que
    venía fallando de forma intermitente) usando el mismo mecanismo de
    .invoke() plano que ya funciona bien en _generar_respuesta."""
    valores = {"correctness": 0.0, "faithfulness": 0.0, "relevance": 0.0, "razon": ""}
    for linea in texto.strip().splitlines():
        if ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        clave = clave.strip().lower()
        valor = valor.strip()
        if clave in ("correctness", "faithfulness", "relevance"):
            try:
                valores[clave] = float(valor)
            except ValueError:
                pass
        elif clave in ("razon", "razón", "reason"):
            valores["razon"] = valor
    return PuntajeCalidad(
        correctness=valores["correctness"],
        faithfulness=valores["faithfulness"],
        relevance=valores["relevance"],
        razon=valores["razon"] or "(sin razón parseada)",
    )


def _juzgar(pregunta: str, esperado: str, respuesta: str, fichas: list) -> PuntajeCalidad:
    contexto = "\n\n".join(f.page_content for f in fichas)
    judge = ChatOpenAI(model=JUDGE_MODEL, temperature=0)
    prompt = f"""Evalúa la respuesta de un sistema de preguntas y respuestas con puntajes de 0.0 a 1.0.

- correctness: coincide con la respuesta esperada.
- faithfulness: cada afirmación está respaldada por el contexto recuperado.
- relevance: responde directamente la pregunta.

Pregunta: {pregunta}
Respuesta esperada: {esperado}
Contexto recuperado: {contexto}
Respuesta real: {respuesta}

Responde EXACTAMENTE en este formato, una línea por cada uno, sin nada más:
correctness: <número entre 0.0 y 1.0>
faithfulness: <número entre 0.0 y 1.0>
relevance: <número entre 0.0 y 1.0>
razon: <una frase breve>"""
    texto = judge.invoke(prompt).content
    return _parsear_puntajes(texto)


def correr_experimento() -> list[dict[str, Any]]:
    vs = _vector_store()
    filas = []

    for i, item in enumerate(QUALITY_DATASET):
        for version, retrieval_fn in [
            ("sin_rerank", _retrieval_sin_rerank),
            ("con_rerank", _retrieval_con_rerank),
        ]:
            try:
                inicio = time.time()
                fichas = retrieval_fn(vs, item["pregunta"])
            except Exception as e:
                print(f"⚠️  Falló RETRIEVAL en item {i} versión {version}: {e!r}\n")
                continue

            try:
                respuesta = _generar_respuesta(item["pregunta"], fichas)
                latencia = time.time() - inicio
            except Exception as e:
                print(f"⚠️  Falló GENERAR_RESPUESTA en item {i} versión {version}: {e!r}\n")
                continue

            try:
                puntaje = _juzgar(item["pregunta"], item["esperado"], respuesta, fichas)
            except Exception as e:
                print(f"⚠️  Falló JUZGAR en item {i} versión {version}: {e!r}\n")
                continue

            filas.append({
                "item": i,
                "version": version,
                "correctness": puntaje.correctness,
                "faithfulness": puntaje.faithfulness,
                "relevance": puntaje.relevance,
                "latencia_s": latencia,
                "razon": puntaje.razon,
            })
    return filas


def imprimir_comparacion(filas: list[dict[str, Any]]) -> None:
    print(f"{'versión':<14} {'correct.':>9} {'faithful.':>10} {'relev.':>8} {'latencia':>10}")
    print("-" * 60)
    for f in filas:
        print(
            f"{f['version']:<14} "
            f"{f['correctness']:>9.2f} "
            f"{f['faithfulness']:>10.2f} "
            f"{f['relevance']:>8.2f} "
            f"{f['latencia_s']:>9.2f}s"
        )
        print(f"  ↳ {f['razon']}")

    # Promedio por versión — el resumen que va directo al informe
    print("\n" + "=" * 60)
    print("PROMEDIO POR VERSIÓN")
    print("=" * 60)
    for version in ("sin_rerank", "con_rerank"):
        subset = [f for f in filas if f["version"] == version]
        n = len(subset)
        if n == 0:
            print(f"{version:<14} (sin datos — todos los ítems fallaron para esta versión)")
            continue
        print(
            f"{version:<14} "
            f"correctness={sum(f['correctness'] for f in subset)/n:.2f}  "
            f"faithfulness={sum(f['faithfulness'] for f in subset)/n:.2f}  "
            f"relevance={sum(f['relevance'] for f in subset)/n:.2f}  "
            f"latencia={sum(f['latencia_s'] for f in subset)/n:.2f}s"
        )


if __name__ == "__main__":
    filas = correr_experimento()
    imprimir_comparacion(filas)