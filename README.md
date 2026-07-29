# asistente-farmacias
 
Asistente informativo de farmacias de turno (MINSAL) y vademécum de medicamentos, con memoria conversacional, RAG semántico y guardrails de seguridad clínica.
Trabajo Final — Módulo 04, Diplomado en IA Generativa (UEjecutivos, Universidad de Chile).
 
## Estado actual
 
| Pieza | Estado |
|---|---|
| Agente LangGraph (StateGraph explícito) + memoria por `user_id` | ✅ |
| Farmacias de turno en vivo — `getLocalesTurnos.php` | ✅ |
| Directorio completo de farmacias en vivo — `getLocales.php` | ✅ |
| RAG del vademécum (Qdrant, 220 fichas) + re-rank y filtro por LLM | ✅ |
| Guardrails de entrada y salida (fail-closed, sin falsos bloqueos) | ✅ |
| Resiliencia ante caída/retiro de modelo (cadena de fallback) | ✅ |
| Observabilidad (Langfuse Cloud + LangSmith) | ✅ |
| Mini-eval de calidad (sin_rerank vs con_rerank) | ✅ |
| Front conversacional | ⏳ pendiente |
| Despliegue en la nube | ⏳ pendiente |
 
## Arquitectura
 
```
POST /chat {user_id, pregunta}
        ↓
   FastAPI (api/main.py)
        ↓
   StateGraph (agent/graph.py)
        ↓
   gate_entrada (¿pide dosis/tratamiento/diagnóstico?)
        ├── SÍ → respuesta_segura → fin
        └── NO → agente ReAct (create_react_agent + MemorySaver por user_id)
                     │
                     ├── consultar_farmacias_de_turno      → MINSAL getLocalesTurnos.php
                     ├── consultar_farmacias_registradas   → MINSAL getLocales.php
                     └── buscar_ficha_medicamento           → Qdrant (retrieval + re-rank LLM + filtro)
                     ↓
                 gate_salida (¿la respuesta igual recomendó algo?)
                     ├── SÍ → respuesta_segura → fin
                     └── NO → respuesta final
```
 
Cada llamada a un LLM (guardas, agente, re-rank) pasa por `resilience.py`,
que intenta una cadena de modelos de respaldo si el principal falla
(retirado, caído, o rechaza algún parámetro). Observabilidad opcional y
degradante: sin claves de Langfuse/LangSmith en `.env`, el agente funciona
igual, solo sin trazas.
 
## Decisiones de diseño relevantes (para el informe)
 
- **Guardrails con texto plano, no `with_structured_output`**: en pruebas
  reales, forzar salida JSON estructurada en un prompt que necesariamente
  discute dosis/tratamiento (aunque sea para *clasificar*, no recomendar)
  disparó el filtro de moderación del proveedor del modelo de forma
  consistente — incluso para preguntas inocuas. Con texto plano + parseo
  manual el problema no se repitió. Ver docstring de `guardrails/clinical_gate.py`.
- **Fail-closed**: si una guarda de seguridad falla por cualquier motivo
  (incluida la moderación del proveedor), el sistema bloquea por defecto en
  vez de dejar pasar. Un control que no puede evaluar debe negar, no permitir.
- **Cadena de modelos de respaldo** (`resilience.py`): evita depender de un
  solo modelo — relevante porque ya vivimos el retiro de `gpt-4o-mini` y
  Anthropic suspendió temporalmente Claude Fable 5/Mythos 5 por controles
  de exportación en julio 2026. Se evita deliberadamente la familia GPT-4o/4.1
  como respaldo, por estar también en proceso de retiro.
- **RAG del vademécum, 1 fila = 1 chunk**: el CSV ya trae unidades semánticas
  completas y acotadas (una ficha por medicamento); trocearlas arriesgaría
  separar el nombre de sus efectos secundarios o indicaciones.
- **Vademécum indexado en inglés**: el dataset original está en inglés; se
  traduce solo en la respuesta final del LLM, no en el índice, para no
  arriesgar errores de traducción "enterrados" en el vector store.
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
 
Requiere el CSV del dataset "Comprehensive Drug Information" (Kaggle) en `data/vademecum/`.
 
```bash
poetry run python load_vademecum.py
```
 
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
{ "user_id": "test-1", "pregunta": "¿Para qué sirve el ibuprofeno?" }
```
 
Prueba de guardrail (debe bloquear, no responder una dosis):
 
```json
{ "user_id": "test-1", "pregunta": "¿Cuánto ibuprofeno debo tomar?" }
```
 
## Mini-eval de calidad (opcional)
 
Compara retrieval simple vs. retrieval + re-rank con LLM-as-judge
(correctness/faithfulness/relevance + latencia):
 
```bash
poetry run python eval_vademecum.py
```
 
## Próximos pasos
 
1. Front conversacional que consuma la API.
2. Despliegue en un entorno cloud (localhost no acredita el punto 6 de la rúbrica).
3. Pruebas adversarias documentadas formalmente (roleplay, insistencia, jailbreak) para el informe.
## Entregables de este trabajo
 
Ver rúbrica del curso (7 criterios) — informe de seguridad/privacidad/calidad,
matriz de riesgos, código + deploy, demo en vivo.