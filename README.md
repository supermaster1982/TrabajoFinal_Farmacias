# asistente-farmacias

Asistente informativo de farmacias de turno (MINSAL) y vademécum de medicamentos, con memoria conversacional, RAG semántico y guardrails de seguridad.
Trabajo Final — Módulo 04, Diplomado en IA Generativa (UEjecutivos, Universidad de Chile).

## Estado actual

| Pieza | Estado |
|---|---|
| Agente LangGraph + memoria por `user_id` | ✅ Funcionando |
| Farmacias de turno (API MINSAL en vivo) | ✅ Funcionando — `getLocalesTurnos.php` |
| Directorio completo de farmacias (API MINSAL en vivo) | ✅ Funcionando — `getLocales.php` |
| RAG del vademécum (Qdrant + 220 fichas de medicamentos) | ✅ Funcionando |
| Observabilidad (Langfuse Cloud + LangSmith) | ✅ Funcionando |
| Guardrails robustos (más allá del prompt básico) | ⏳ Pendiente |
| Front conversacional | ⏳ Pendiente |
| Despliegue en la nube | ⏳ Pendiente |

## Arquitectura

```
POST /chat {user_id, pregunta}
↓
FastAPI (api/main.py)
↓
LangGraph agent (agent/graph.py) — create_react_agent + MemorySaver(thread_id=user_id)
↓
┌──────────────────────────┬──────────────────────────┬─────────────────────────┐
tool_minsal.py tool_minsal.py tool_rag.py
consultar_farmacias_de_turno consultar_farmacias_registradas buscar_ficha_medicamento
→ getLocalesTurnos.php → getLocales.php → Qdrant (vademecum_medicamentos)
```

Observabilidad opcional y degradante: si no hay claves de Langfuse/LangSmith en el `.env`, el agente funciona exactamente igual, solo sin trazas.

## Requisitos previos

- Python 3.11+
- Poetry
- API key de OpenAI
- Cluster de Qdrant Cloud (URL + API key)
- (Opcional) Cuenta de Langfuse Cloud y/o LangSmith, para observabilidad

## Setup local

```bash
cp .env.example .env   # completa OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY (y Langfuse/LangSmith si quieres trazas)
poetry install --with dev
```

## Poblar el vademécum en Qdrant (una sola vez)

Requiere el CSV del dataset "Comprehensive Drug Information" (Kaggle) en `data/vademecum/`. Ver comentario en `load_vademecum.py` para el nombre exacto de archivo esperado.

```bash
poetry run python load_vademecum.py
```

Debería terminar con `✅ Índice listo · 220 vectores en Qdrant/vademecum_medicamentos`.

## Correr el servidor

```bash
poetry run uvicorn asistente_farmacias.api.main:app --reload --port 8000 --app-dir src
```

Abre **http://localhost:8000/docs** y prueba `POST /chat`:

```json
{ "user_id": "test-1", "pregunta": "¿Hay alguna farmacia de turno en Providencia?" }
```

Segundo turno, **mismo `user_id`**, para probar memoria:

```json
{ "user_id": "test-1", "pregunta": "¿Y cuál es su dirección?" }
```

Pregunta de vademécum:

```json
{ "user_id": "test-1", "pregunta": "¿Para qué sirve el Aspirin?" }
```

## Chunking del vademécum — estrategia y justificación

1 fila del CSV = 1 chunk, sin splitting. A diferencia de un documento largo, cada fila ya es una unidad semántica completa y acotada (una ficha de medicamento) — trocearla arriesgaría separar el nombre del medicamento de sus efectos secundarios o indicaciones en chunks distintos.

## Idioma del vademécum

El índice está en inglés (idioma original del dataset de Kaggle). La traducción al español ocurre solo en la respuesta final del LLM, no en el índice — así se evita que un error de traducción quede "enterrado" en el vector store y se repita en cada respuesta.

## Próximos pasos

1. Guardrails robustos: nodo de validación de entrada/salida (más allá del prompt actual) + set de pruebas adversarias (`tests/adversarial/`).
2. Front conversacional que consuma la API.
3. Despliegue en un entorno cloud (localhost no acredita el punto 6 de la rúbrica).

## Entregables de este trabajo

Ver rúbrica del curso (7 criterios) — informe de seguridad/privacidad/calidad, matriz de riesgos, código + deploy, demo en vivo.