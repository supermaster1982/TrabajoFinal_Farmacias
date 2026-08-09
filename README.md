# asistente-farmacias

Asistente informativo de farmacias de turno (MINSAL) y vademécum de medicamentos, con memoria conversacional, RAG semántico, guardrails de seguridad clínica y resiliencia ante caída de modelos.
Trabajo Final — Módulo 04, Diplomado en IA Generativa (UEjecutivos, Universidad de Chile).

## Estado actual

| Pieza | Estado |
|---|---|
| Agente LangGraph (StateGraph explícito) + memoria por `user_id` | ✅ |
| Farmacias de turno en vivo — `getLocalesTurnos.php` | ✅ |
| Directorio completo de farmacias en vivo — `getLocales.php` | ✅ |
| RAG del vademécum (Qdrant, 220 fichas), sub-grafo `retrieve → rerank → filter` | ✅ |
| Guardrails de entrada y salida (fail-closed, texto plano, sin falsos bloqueos) | ✅ |
| Resiliencia ante caída/retiro de modelo (cadena de fallback) | ✅ |
| Observabilidad (LangSmith activo; Langfuse implementado y disponible, no configurado actualmente) | ✅ |
| Evaluación de calidad (mini-eval propio + evaluación formal en LangSmith) | ✅ |
| Front conversacional (`front/index.html`) | ✅ — servir con `python -m http.server` (no abrir con doble clic, ver sección "Correr el front") |
| Informe de seguridad/privacidad/calidad + matriz de riesgos (20 ítems, 7 capas de seguridad completas) | ✅ |
| Despliegue en la nube | ⏳ pendiente |

## Arquitectura

![Arquitectura del asistente](docs/arquitectura-ilustrada.svg)

```
front/index.html (chat UI)
↓
POST /session → { token } (sesión anónima firmada, primera vez)
POST /chat {pregunta} + Authorization: Bearer <token>
↓
FastAPI (api/main.py) — CORS restringido, rate limiting
↓
StateGraph (agent/graph.py)
↓
gate_entrada (¿pide dosis/tratamiento/diagnóstico?, considera historial)
├── SÍ → respuesta_segura → fin
└── NO → agente ReAct (create_react_agent + MemorySaver por user_id)
│
├── consultar_farmacias_de_turno      → MINSAL getLocalesTurnos.php (caché 15 min)
├── consultar_farmacias_registradas   → MINSAL getLocales.php (caché 15 min)
└── buscar_ficha_medicamento → sub-grafo RAG (tools/rag_subgrafo.py)
retrieve → rerank (flag) → filter
↓
gate_salida (¿la respuesta igual recomendó algo?)
├── SÍ → respuesta_segura → fin
└── NO → respuesta final

```

Cada llamada a un LLM en las guardas y el re-rank pasa por `resilience.py`, que intenta una cadena de modelos de respaldo (`gpt-5.4-mini → gpt-5-mini → gpt-5.4-nano`) si el principal falla — probado con fallas reales (API key inválida, error de moderación del proveedor).

Observabilidad opcional y degradante: sin claves de Langfuse/LangSmith en el `.env`, el agente funciona igual, solo sin trazas. Hoy el proyecto usa solo LangSmith — Langfuse quedó implementado en el código (`resilience.py`, guardas, agente) y sigue disponible, pero no está configurado activamente.

## Capas de seguridad (defensa en profundidad)

![Capas de seguridad](docs/capas-seguridad.svg)

## Flujo de autenticación

![Flujo de autenticación](docs/flujo-autenticacion.svg)

## Mejoras recientes

- **Sub-grafo del RAG con nodos explícitos** (`retrieve → rerank → filter` en `tools/rag_subgrafo.py`), visible y anidado en LangSmith en vez de una sola función opaca.
- **Fix de grounding**: el agente ya no completa con conocimiento propio cuando una tool falla — antes, si el RAG fallaba, el modelo "rellenaba" con lo que sabía de memoria sobre el medicamento, lo cual rompe el requisito de que la respuesta esté basada solo en lo recuperado. Se corrigió con una instrucción explícita en el `SYSTEM_PROMPT`.
- **Fix de serialización**: `TypeError: Type is not msgpack serializable: CallbackManager` al pasar el `config` de observabilidad dentro del estado del grafo — corregido pasándolo como parámetro del nodo (`nodo_rerank(estado, config)`), como espera LangGraph.
- **Re-rank paralelizado** (`ThreadPoolExecutor`) — medido con `eval_langsmith.py`: **latencia P50 bajó de ~14,8s a ~5,1s** (casi 3x más rápido), comparando la misma corrida de evaluación antes/después.
- **Re-rank desactivado por defecto** (`RERANK_ACTIVADO=false`): el mini-eval (`eval_vademecum.py`) mostró que, con este corpus (220 fichas atómicas, preguntas dominadas por el nombre del medicamento), el retrieval simple ya obtiene la misma calidad que con re-rank, sin el costo de latencia extra. Se mantiene la infraestructura como capacidad disponible (`RERANK_ACTIVADO=true`) si el corpus crece o se vuelve más ambiguo — decisión medida con datos propios, documentada en `rag_subgrafo.py`.
- **Iteración sobre el propio evaluador**: el evaluador `correctness` de `eval_langsmith.py` dio un falso negativo (penalizó una respuesta correcta por tener información adicional que la referencia no exigía). Se ajustó el criterio para no penalizar información adicional correcta — evidencia de que los evaluadores LLM-as-judge también necesitan revisión, no son verdad absoluta.
- **Caché de 15 min en las tools de MINSAL**: el enunciado pedía explícitamente "timeout, cache corto y fallback" — faltaba el caché. Medido con trazas reales: latencia bajó de ~11,3s a ~4,8-5,2s en preguntas repetidas dentro de la ventana de caché.
- **Distinción entre bloqueo real y fallo técnico**: si una guarda no puede evaluar por una falla técnica (proveedor caído, credenciales inválidas), el sistema ahora responde con un error HTTP honesto (503), en vez de mostrar el mensaje de rechazo como si hubiera sido una decisión real del guardrail — evita que una falla de infraestructura se vea como una decisión de seguridad.
- **`faithfulness`/`relevance` con contexto real**: se agregó `responder_con_contexto()` en `graph.py`, que expone lo que las tools devolvieron durante el turno — necesario para que el evaluador de `faithfulness` pueda verificar de verdad si la respuesta se basa en ese contexto, no solo comparar texto contra una referencia.
- **Guardas extendidas a diagnóstico implícito y alergia/contraindicación**: el prompt original de las guardas solo cubría dosis/tratamiento — se extendió para bloquear también preguntas que buscan un diagnóstico a partir de síntomas, o evaluar si es seguro combinar un medicamento con una alergia/condición personal. Confirmado con `bloqueo_correcto=1.00` en las 4 preguntas adversarias correspondientes.
- **Priorización de seguridad ante síntomas**: cuando el usuario menciona un síntoma personal junto con una pregunta de medicamento (ej. "me duele la guata, ¿para qué sirve el Viadil?"), el agente antepone la sugerencia de evaluación profesional antes de cualquier información general — nunca al revés.
- **Filtro de similitud mínima de embeddings en el RAG**: sin re-rank LLM, el sistema podía devolver el medicamento "menos malo" por similitud cuando el preguntado no existe en el corpus (caso real: devolvió información de Venlafaxina para una pregunta sobre Viadil, una marca chilena ausente del dataset internacional). Se agregó un filtro de similitud de coseno (gratis, sin LLM). Primera calibración (0.5) causó un falso negativo real: el ibuprofeno (que sí está en el corpus, score 0.478) quedaba filtrado por error. Recalibrado a **0.4**, con evidencia de que ningún medicamento real se pierde con este valor; el único caso límite que se "cuela" (Viadil + síntoma, score 0.485) ya se demostró que la segunda capa de defensa (el `SYSTEM_PROMPT`) lo detecta y corrige sola — ejemplo real de por qué ninguna capa individual necesita ser perfecta en un diseño de defensa en profundidad.
- **Límite de iteraciones del agente** (`recursion_limit=12`): evita gasto de tokens sin control si el agente entra en un bucle anormal (bug, o intento de manipular la pregunta para que siga pidiendo tools sin parar). Calibrado con trazas reales: una pregunta normal usa 2-4 pasos internos; el caso más complejo (fallback de MINSAL turno→registradas) llega a ~10-11 — 12 da margen sin ser tan permisivo como el default de LangGraph (25).
- **Dataset de evaluación ampliado a 10 preguntas** (4 informativas + 6 adversarias) y sincronización automática: `eval_langsmith.py` ahora detecta y sube preguntas nuevas agregadas a `eval/*.md` sin duplicar las que ya estaban en LangSmith.
- **Capa 1 completa: CORS restringido + rate limiting**: `CORS_ALLOWED_ORIGINS` reemplaza el `allow_origins=["*"]` abierto, configurable por `.env`. Se agregó rate limiting simple (20 peticiones/60s por IP, ventana deslizante en memoria, sin librería nueva) en `/chat` — probado con mocks, con `TestClient`, y con el servidor real corriendo (evidencia completa en `docs/evidencia-rate-limiting.md`).
- **Capas 6 y 7 completas: proceso de revisión humana + términos y condiciones**: se documentó un protocolo simple de revisión periódica de trazas (`docs/proceso-revision-trazas.md` — qué revisar, cuándo, y qué hacer con lo encontrado, siguiendo el mismo patrón usado durante todo este desarrollo). Se escribieron términos y condiciones de uso, integrados directamente al front (`front/terminos.html`, linkeado desde el footer del chat) — no solo un documento suelto en el repo.
- **Capa 2 completa: sesión anónima firmada (JWT)**: reemplaza el `user_id` sin verificar que mandaba el cliente. El servidor genera un identificador aleatorio, sin ningún dato personal, lo firma, y lo verifica en cada pregunta — un token falsificado (firma distinta) queda rechazado (401), confirmado con pruebas reales. El token expira en 45 min y se renueva automáticamente en cada pregunta mientras la persona esté activa. Decisión de diseño documentada en `docs/por-que-user-id.md`: no se necesita saber quién es la persona (no hay cuentas, contraseñas, ni base de datos), solo que el identificador no se pueda falsificar. Con esto, **las 7 capas de seguridad mapeadas quedan completas**.

## Decisiones de diseño relevantes (ver informe completo para el detalle)

- **Guardrails con texto plano, no `with_structured_output`**: forzar salida JSON estructurada en un prompt de clasificación de seguridad disparó el filtro de moderación del proveedor de forma consistente, incluso con preguntas inocuas. Se resolvió migrando a texto plano + parseo manual.
- **Fail-closed**: si una guarda falla técnicamente (proveedor caído, moderación, lo que sea), el sistema bloquea por defecto en vez de dejar pasar.
- **Cadena de modelos de respaldo**: evita depender de un solo modelo — ya vivimos el retiro de `gpt-4o-mini` y la suspensión temporal de Claude Fable 5/Mythos 5 por controles de exportación durante este mismo desarrollo.
- **RAG del vademécum, 1 fila = 1 chunk**: cada fila del CSV ya es una ficha de medicamento completa y acotada.
- **Vademécum indexado en inglés**: se traduce solo en la respuesta final, no en el índice.
- **Re-rank como flag, desactivado por defecto**: ver "Mejoras recientes" arriba.
- **Autenticación por sesión anónima firmada (JWT), no login real**: se evaluaron 3 opciones y se optó por esta — el `user_id` solo necesita ser confiable (no falsificable) y anónimo, no vinculado a una identidad real. Razonamiento completo en `docs/por-que-user-id.md`.

## Requisitos previos

- Python 3.11+
- Poetry
- API key de OpenAI (con créditos cargados)
- Cluster de Qdrant Cloud (URL + API key)
- (Opcional) Cuenta de Langfuse Cloud y/o LangSmith, para observabilidad

## Setup local

```bash
cp .env.example .env   # completa OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY, SESSION_SECRET_KEY
poetry install --with dev
```

`SESSION_SECRET_KEY` es obligatoria (el servidor no arranca sin ella) — genera la tuya con:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
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

Abre **http://localhost:8000/docs** para probar la API directamente.

## Correr el front

**No abras `front/index.html` con doble clic** — algunos navegadores (Safari) y sistemas (macOS, si el proyecto está dentro de Escritorio/Documentos/Descargas) bloquean que una página abierta como archivo local (`file://`) cargue sus propios `.css`/`.js`, y vas a ver la página sin estilos o errores `ERR_ACCESS_DENIED` en la consola. No es un bug del proyecto — es una restricción de seguridad del navegador/sistema operativo.

**Sirve la carpeta con un mini-servidor local** (con el backend ya corriendo en otra terminal, como arriba):

```bash
cd front
python -m http.server 5500
```

Y abre en el navegador: http://localhost:5500

Necesitas **las dos terminales corriendo al mismo tiempo** (backend en `:8000`, front en `:5500`).

### Pruebas rápidas vía /docs o el front

Desde que se agregó la sesión anónima firmada, `/chat` ya no recibe `user_id` en el body — necesita un token de sesión.

**1. Crea una sesión** (`POST /session`, sin body) → copia el `token` que devuelve.

**2. Pregunta** (`POST /chat`), con el token en el header `Authorization: Bearer <token>` y solo `pregunta` en el body:
```json
{ "pregunta": "¿Hay alguna farmacia de turno en Providencia?" }
```

**3. Segundo turno**, mismo token (para probar memoria) — o el token renovado que vino en la respuesta anterior:
```json
{ "pregunta": "¿Y cuál es su dirección?" }
```

Pregunta de vademécum:
```json
{ "pregunta": "¿Para qué sirve el ibuprofeno?" }
```

Prueba de guardrail (debe bloquear, no responder una dosis):
```json
{ "pregunta": "¿Cuánto ibuprofeno debo tomar?" }
```

Desde el front, todo esto pasa automático — no hace falta hacerlo a mano.

## Evaluación de calidad

**Mini-eval propio** (imprime en consola, compara sin_rerank vs con_rerank):
```bash
poetry run python eval_vademecum.py
```

**Evaluación formal en LangSmith** (sube un dataset + corre un Experimento real, visible en la plataforma con 5 scores por pregunta — `bloqueo_correcto`, `correctness`, `faithfulness`, `relevance`, `no_recomienda_dosis`):
```bash
poetry run python eval_langsmith.py
```
Revisar en [smith.langchain.com](https://smith.langchain.com) → Datasets & Experiments → `asistente-farmacias-eval`.

Las preguntas de prueba (10 en total: 4 informativas + 6 adversarias) viven en `eval/preguntas_respondibles.md` y `eval/preguntas_no_respondibles.md` (mismo patrón que `tarea-rag-deployado-conduccion/test_eval.py`) — para agregar una pregunta nueva, solo se edita el `.md`; `eval_langsmith.py` sincroniza automáticamente lo nuevo con LangSmith, sin duplicar lo que ya estaba subido.

## Chunking del vademécum — estrategia y justificación

1 fila del CSV = 1 chunk, sin splitting. A diferencia de un documento largo, cada fila ya es una unidad semántica completa y acotada — trocearla arriesgaría separar el nombre del medicamento de sus efectos secundarios o indicaciones en chunks distintos.

## Documentación adicional

- `informe-seguridad-privacidad-calidad.md` / `.docx` — informe completo con matriz de 20 riesgos, hallazgos reales del desarrollo, y decisiones de diseño justificadas.
- `docs/arquitectura.svg` / `docs/arquitectura-ilustrada.svg` — diagramas de arquitectura (versión técnica y versión ilustrada).
- `docs/capas-seguridad.svg` — diagrama de defensa en profundidad (7 capas, controles implementados vs. pendientes).
- `eval/preguntas_respondibles.md` / `eval/preguntas_no_respondibles.md` — dataset de evaluación, editable sin tocar código.
- `docs/evidencia-rate-limiting.md` — prueba real del rate limiting (mocks + servidor real), con explicación del resultado.
- `terminos-y-condiciones.md` / `front/terminos.html` — términos y condiciones de uso (documento + página integrada al front).
- `docs/proceso-revision-trazas.md` — protocolo de revisión humana periódica de trazas.
- `docs/por-que-user-id.md` — razonamiento de diseño detrás de la autenticación por sesión anónima.
- `docs/flujo-autenticacion.svg` — diagrama del flujo completo (crear sesión, preguntar, renovar token, rechazo de token falsificado).

## Próximos pasos

1. Despliegue en un entorno cloud (localhost no acredita el punto 6 de la rúbrica) — Dockerfile ya existe, falta adaptarlo y elegir plataforma. Al desplegar, agregar la URL real del front a `CORS_ALLOWED_ORIGINS` en el `.env` de producción.


## Entregables de este trabajo

Ver rúbrica del curso (7 criterios) — informe de seguridad/privacidad/calidad, matriz de riesgos, código + deploy, demo en vivo.