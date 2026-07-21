# asistente-farmacias

Asistente informativo de farmacias de turno (MINSAL) y vademécum de medicamentos, con memoria conversacional y guardrails de seguridad.
Trabajo Final — Módulo 04, Diplomado en IA Generativa (UEjecutivos, Universidad de Chile).

## ⚠️ Estado actual: Stage 0 — esqueleto (walking skeleton)

Este commit valida que la tubería completa funciona de punta a punta, **con
tools simuladas** (stub). Todavía NO consulta la API real de MINSAL ni un
vector store real. El objetivo de esta etapa es probar, antes de invertir
tiempo en las integraciones reales:

- que el agente LangGraph elige correctamente entre las dos tools,
- que la memoria por `user_id` funciona (dos turnos dependientes),
- que FastAPI expone el contrato esperado.

Cada tool stub tiene un bloque `TODO` indicando exactamente qué falta y en
qué rama se resuelve.

## Arquitectura (stage 0)

```
POST /chat {user_id, pregunta}
        ↓
   FastAPI (api/main.py)
        ↓
   LangGraph agent (agent/graph.py) — create_react_agent + MemorySaver(thread_id=user_id)
   (el checkpointer vive dentro de graph.py; si más adelante crece, se separa a su propia carpeta)
        ↓
   ┌────────────────────────┬─────────────────────────┐
   tool_minsal.py (STUB)     tool_rag.py (STUB)
   → API MINSAL real         → Qdrant real
     (rama feature/tool-minsal) (rama feature/rag-vademecum)
```

## Requisitos previos

- Python 3.11+
- Poetry
- Una API key de OpenAI (para el LLM que decide qué tool usar)

## Setup local

```bash
cp .env.example .env   # completa OPENAI_API_KEY
poetry install --with dev
```

## Correr el servidor

```bash
poetry run uvicorn asistente_farmacias.api.main:app --reload --port 8000 --app-dir src
```

Abre **http://localhost:8000/docs** y prueba `POST /chat`:

```json
{ "user_id": "test-1", "pregunta": "¿Hay alguna farmacia de turno en Providencia?" }
```

Y para probar la memoria, un segundo turno **con el mismo `user_id`**:

```json
{ "user_id": "test-1", "pregunta": "¿Y cuál es su dirección?" }
```

Si el agente responde sin que vuelvas a mencionar Providencia, la memoria
por `user_id` está funcionando.

Prueba también con un `user_id` distinto para confirmar que las
conversaciones no se mezclan entre usuarios.

## Próximos pasos (ramas)

Nota: no hay carpetas vacías "reservadas" para esto — cada una se crea recién
en la rama donde se necesita, junto con el primer archivo real que la usa.

1. `feature/tool-minsal` — reemplazar el stub por la API real de MINSAL (timeout, normalización, fallback).
2. `feature/rag-vademecum` — indexar el dataset de Kaggle en Qdrant y conectar la tool real (agrega `data/vademecum/`).
3. `feature/guardrails` — guardrail robusto (no solo prompt) + pruebas adversarias (agrega `tests/adversarial/`).
4. `feature/api-front` — front conversacional que consuma la API.
5. `feature/deploy` — Dockerfile validado + despliegue cloud.
6. Tests unitarios y notebooks de exploración: se agregan cuando surja el primer caso real que los necesite, no antes.

## Entregables de este trabajo

Ver rúbrica del curso (7 criterios) — informe de seguridad/privacidad/calidad,
matriz de riesgos, código + deploy, demo en vivo.
