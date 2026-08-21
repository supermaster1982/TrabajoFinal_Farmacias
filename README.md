# Asistente-farmacias

Asistente informativo de farmacias de turno (MINSAL) y vademécum de medicamentos (dos fuentes: internacional y chilena vía MCP), con memoria conversacional, RAG semántico, guardrails de seguridad clínica y resiliencia ante caída de modelos.
Trabajo Final — Módulo 04, Diplomado en IA Generativa (UEjecutivos, Universidad de Chile).

## ¿Qué responde y qué no?

![Árbol de decisión: cuándo responde y cuándo no](docs/flujo_responde_o_no_responde.svg)

| Pregunta | ¿Responde? |
|---|---|
| "¿Para qué sirve el Paracetamol?" | ✅ Sí — información general, con fuente citada |
| "¿Qué farmacia está de turno en Providencia?" | ✅ Sí — dato en vivo de MINSAL |
| "¿Cuánto ibuprofeno debo tomar?" | ❌ No — pide dosis personalizada |
| "Me duele la cabeza, ¿para qué sirve el Paracetamol?" | ❌ No — síntoma + medicamento en el mismo mensaje |
| "Me duele la cabeza, ¿qué enfermedad tengo?" | ❌ No — diagnóstico implícito |
| "¿Puedo mezclar amoxicilina con alcohol?" | ❌ No — interacción personalizada |
| "¿Va a llover mañana?" | ❌ No — fuera del dominio del asistente |

## Inicio rápido

Para alguien que nunca vio este proyecto — los pasos mínimos, en orden, sin explicaciones (esas están más abajo si las necesitas).

**1. Clona y entra a la carpeta**
```bash
git clone https://github.com/genval/TrabajoFinal_Farmacias.git
cd TrabajoFinal_Farmacias
```

**2. Consigue las credenciales que necesitas**
- **OpenAI**: tu propia API key, con créditos cargados — [platform.openai.com](https://platform.openai.com).
- **Qdrant Cloud**: crea un cluster gratuito en [cloud.qdrant.io](https://cloud.qdrant.io) → copia la URL y la API key.
- **SESSION_SECRET_KEY**: la generas tú misma en el paso 4, no hay que "conseguirla" de ningún lado.
- **Vademécum chileno (`vademecum.json`)**: material de clase provisto por el profesor, no se distribuye en este repo (contenido de terceros) — pídeselo directamente si necesitas correr esa fuente. Sin él, el sistema funciona igual usando solo el vademécum de Kaggle.

**3. Instala las dependencias**
```bash
poetry install --with dev
```

**4. Configura tu `.env`**
```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # copia lo que imprima
```
Abre `.env` y completa `OPENAI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, y pega el valor generado en `SESSION_SECRET_KEY`. `GEN_MODEL` es obligatoria (ej. `GEN_MODEL=gpt-5.6-luna`); `GUARD_MODEL` es opcional (usa `gpt-5.6-luna` por defecto si no la seteas).

**`LANGSMITH_API_KEY`** — técnicamente el sistema corre sin ella (sin trazas), pero **es necesaria para que el proyecto funcione como está diseñado**: la capa de seguridad "Observabilidad y evaluación" depende de LangSmith tanto para el proceso de revisión de trazas (`docs/proceso-revision-trazas.md`) como para correr la evaluación formal (`eval_langsmith.py`). Consíguela gratis en [smith.langchain.com](https://smith.langchain.com).

**5. Pobla los vademécums en Qdrant (una sola vez cada uno)**
```bash
poetry run python load_vademecum.py          # Kaggle (CSV ya incluido en el repo)
poetry run python load_vademecum_chile.py    # Chileno (requiere vademecum.json, ver paso 2)
```

**6. Si vas a usar el vademécum chileno, levanta primero el servidor MCP** (deja esta terminal corriendo)
```bash
poetry run python servidor_vademecum_chile.py
```
**El orden importa**: este servidor debe estar corriendo *antes* de levantar el backend — el backend se conecta a él al arrancar. Si no tienes el `vademecum.json` (paso 2), puedes saltarte este paso: el sistema sigue funcionando solo con el vademécum de Kaggle.

**7. Levanta el backend, en OTRA terminal** (deja esta también corriendo)
```bash
poetry run uvicorn asistente_farmacias.api.main:app --reload --reload-include ".env" --port 8000 --app-dir src
```

**8. Levanta el front, en OTRA terminal más** (deja esta también corriendo)
```bash
cd front
python3 -m http.server 5500
```

**9. Abre el navegador**

http://localhost:5500

Y prueba preguntando algo como *"¿Para qué sirve el ibuprofeno?"*

Si algo no funciona, revisa la sección "Correr el servidor" / "Correr el front" más abajo — tienen detalle de errores comunes.

## Estado actual

| Pieza | Estado |
|---|---|
| Agente LangGraph (StateGraph explícito) + memoria por `user_id` | ✅ |
| Farmacias de turno en vivo — vía proxy en Cloud Run Santiago (esquiva bloqueo de Cloudflare) | ✅ |
| Directorio completo de farmacias en vivo — vía el mismo proxy | ✅ |
| Fallback de MINSAL: proxy en vivo → snapshot rotulado con fecha → mensaje digno | ✅ |
| RAG del vademécum internacional (Qdrant, Kaggle), `retrieve → filtro → verificación LLM` | ✅ |
| RAG del vademécum chileno (Qdrant, 12,411 fichas), consumido vía **protocolo MCP** — fuente secundaria/fallback | ✅ |
| Citas de fuente obligatorias en cada respuesta (determinístico, no depende del LLM) | ✅ |
| Guardrails de entrada y salida (fail-closed, texto plano, sin falsos bloqueos) | ✅ |
| Bloqueo determinístico de síntoma + medicamento en el mismo mensaje (`gate_entrada`) | ✅ |
| Resiliencia ante caída/retiro de modelo — cadenas independientes para `GEN_MODEL` y `GUARD_MODEL` | ✅ |
| Observabilidad (LangSmith activo; Langfuse implementado y disponible, no configurado actualmente) | ✅ |
| Evaluación formal en LangSmith (22 preguntas, 6 métricas) + comparación factorial 3×3 de modelos | ✅ |
| Front conversacional (`front/index.html`) | ✅ — servir con `python3 -m http.server` (no abrir con doble clic, ver sección "Correr el front") |
| Informe de seguridad/privacidad/calidad + matriz de riesgos (23 ítems, 7 capas de seguridad completas) | ✅ |
| Despliegue en la nube (backend + front) | ✅ |
| Despliegue del servidor MCP en producción | ⏳ pendiente (coordinar con el equipo) |

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
gate_entrada (¿pide dosis/tratamiento/diagnóstico? ¿síntoma + medicamento en el mismo mensaje?)
├── SÍ → respuesta_segura → fin
└── NO → agente ReAct (create_react_agent + MemorySaver por user_id)
│
├── consultar_farmacias_de_turno      → MINSAL vía proxy (caché 15 min)
├── consultar_farmacias_registradas   → MINSAL vía proxy (caché 15 min)
├── buscar_ficha_medicamento          → RAG directo (Kaggle) — retrieve → filtro → verificación LLM
└── buscar_ficha_medicamento_chile    → CLIENTE MCP → servidor_vademecum_chile.py (proceso aparte)
↓
gate_salida (¿la respuesta igual recomendó algo?)
├── SÍ → respuesta_segura → fin
└── NO → respuesta_ok (cita de fuente agregada aquí)

```

Detalle del fallback entre las dos fuentes de vademécum (con los tiempos reales medidos):

![Flujo de fallback Kaggle → verificación LLM → vademécum chileno](docs/flujo_fallback_vademecum_kaggle_chile.svg)

## Vademécum chileno vía MCP

El profesor pidió explícitamente que, si se usaba el vademécum chileno que compartió como material de clase, el acceso se implementara "como API o MCP, consumido desde la llamada de la tool" — se eligió **MCP** (Model Context Protocol), siguiendo el patrón de la Clase 5.4 del diplomado.

**Arquitectura de 2 servicios**: `servidor_vademecum_chile.py` es un servidor FastMCP que envuelve la búsqueda real (`tools/rag_subgrafo_chile.py` — retrieve, filtro de similitud 0.54, verificación de relevancia con LLM), sin reimplementarla. `tools/tool_rag_chile.py` es el cliente MCP que el agente usa como una tool más — configurable vía `MCP_VADEMECUM_CHILE_URL` en `.env`, para poder apuntar a producción sin tocar código.

**Es una fuente secundaria, no un reemplazo**: el agente intenta primero `buscar_ficha_medicamento` (Kaggle); solo si esa tool no encuentra nada relevante, intenta `buscar_ficha_medicamento_chile` — mismo patrón de fallback que ya existía entre las dos tools de MINSAL. Por eso el camino de Chile es más lento (~15s vs ~8s del camino de Kaggle): implica dos búsquedas vectoriales completas en vez de una, además de la conexión al servidor MCP.

**Dos bugs reales encontrados y corregidos durante la implementación** (detalle completo en el informe, sección 3.12):
1. `asyncio.run()` fallaba con `uvicorn --reload` por un event loop ya activo — resuelto detectando el loop y usando un hilo aparte cuando hace falta.
2. Un cliente MCP compartido entre preguntas fallaba silenciosamente (nunca llegaba al servidor) — resuelto creando una conexión nueva en cada llamada, sin nada compartido entre requests.

También hubo que resolver un conflicto de dependencias: `langchain-mcp-adapters==0.3.2` (la versión de la clase) exige `langchain-core>=1.3.3`, incompatible con el `langchain-core^0.3.0` que usa el resto de este proyecto. Se usa `langchain-mcp-adapters==0.1.14` en su lugar, sin ese conflicto.

## Resiliencia ante caída o retiro de modelo

`GEN_MODEL` (agente) y `GUARD_MODEL` (guardas de entrada/salida + filtro de similitud de embeddings) son variables independientes, cada una con su propia cadena de fallback — evita el acoplamiento accidental que hubo en una etapa temprana del desarrollo, donde `resilience.py` leía `GEN_MODEL` por error y cambiar el modelo del agente cambiaba sin querer también el de las guardas.

![Cadena de fallback de GUARD_MODEL](docs/cadena-guard-model.svg)

`gate_entrada`, `gate_salida` y el filtro de similitud de embeddings pasan por `invocar_con_fallback()` en `resilience.py`. Fail-closed: si los tres modelos fallan, se bloquea por seguridad en vez de dejar pasar.

![Cadena de fallback de GEN_MODEL](docs/cadena-gen-model.svg)

El agente usa `ChatOpenAI.with_fallbacks()` de LangChain, integrado directo en el modelo que recibe `create_react_agent`. Confirmado con evidencia real en LangSmith: forzando un modelo inválido, el trace muestra la llamada fallida (0.29s) seguida del fallback exitoso (0.91s) dentro del mismo turno, sin error visible para el usuario.

Cadena vigente en ambos roles, elegida con una comparación factorial 3×3 sobre los tres modelos candidatos (detalle completo, con las 5 matrices de métricas, en `docs/eleccion-modelos-gen-guard.md`):

```
gpt-5.6-luna (principal) → gpt-5.4-mini (respaldo 1) → gpt-5.4-nano (respaldo 2)
```

Se sacó deliberadamente `gpt-5-mini` (snapshot `2025-08-07`) de toda cadena — confirmado en logs reales que ya no acepta `temperature` distinto de 1, y OpenAI ya anunció su retiro de la API para el 10 de diciembre de 2026.

Observabilidad opcional y degradante: sin claves de Langfuse/LangSmith en el `.env`, el agente funciona igual, solo sin trazas. Hoy el proyecto usa solo LangSmith — Langfuse quedó implementado en el código (`resilience.py`, guardas, agente) y sigue disponible, pero no está configurado activamente.

## Capas de seguridad (defensa en profundidad)

![Capas de seguridad](docs/capas-seguridad.svg)

## Flujo de autenticación

![Flujo de autenticación](docs/flujo-autenticacion.svg)

**Nota sobre persistencia de sesión:** el token de sesión (JWT, 45 min) se guarda en `localStorage` del navegador y se renueva automáticamente en cada pregunta exitosa mientras la persona esté activa — un simple refresh de página **no** genera una conversación nueva, el historial de la sesión se mantiene mientras el token siga vigente. Ver `docs/por-que-user-id.md`.

## Mejoras recientes

- **Vademécum chileno vía MCP** — ver sección dedicada arriba, y el informe (sección 3.12) para el detalle completo con evidencia.
- **Citas de fuente obligatorias, determinísticas**: el enunciado pide "siempre citando la fuente" — en vez de confiar en que el LLM la mencione, `_extraer_citas()` en `graph.py` arma la cita a partir del texto real que devolvieron las tools, agregándola solo después de que `gate_salida` ya aprobó la respuesta (para no interferir en esa evaluación).
- **Bloqueo determinístico de "síntoma + medicamento en el mismo mensaje"**: movido a `gate_entrada`, sin necesitar buscar nada — más rápido y no depende de si el medicamento existe en algún corpus. `gate_salida` volvió a su forma original (bloquea solo con coincidencia real de indicación con un síntoma de un turno anterior), tras detectar que una versión más amplia bloqueaba de más casos legítimos.
- **Verificación de relevancia con LLM en el RAG**: el filtro de similitud por sí solo no distingue "esto es lo más parecido que hay, aunque no tenga relación" de "esto sí es relevante" — se agregó una verificación adicional (¿la mejor candidata tiene relación real con lo preguntado?) antes de aceptar un resultado, en ambos vademécums.
- **Proxy propio para MINSAL** (Google Cloud Run, `southamerica-west1`): la API de MINSAL está detrás de Cloudflare, que bloquea IP de datacenter extranjeras — confirmado con evidencia real (GitHub Actions, deploy en Render, ambos con 403; Postman desde Chile, funciona). El proxy, con IP chilena, esquiva el bloqueo y restaura el dato en vivo real. Detalle completo en `docs/proxy-minsal.md`.
- **Sincronización del dataset de eval con LangSmith**: `eval_langsmith.py` ahora también *actualiza* preguntas existentes cuyo `tipo`/`esperado` cambió en el `.md` local (antes solo agregaba preguntas nuevas) — sin esto, mover una pregunta de "informativa" a "adversaria" no tenía ningún efecto en corridas futuras.
- **Cadenas de fallback separadas para `GEN_MODEL` y `GUARD_MODEL`**, con `gpt-5.6-luna` elegido en ambos roles tras una comparación factorial 3×3 — ver sección "Resiliencia" arriba y `docs/eleccion-modelos-gen-guard.md` para el detalle completo con evidencia.
- **Sub-grafo del RAG con nodos explícitos** (`retrieve → rerank → filter`), visible y anidado en LangSmith en vez de una sola función opaca — misma estructura para ambos vademécums.
- **Fix de grounding**: el agente ya no completa con conocimiento propio cuando una tool falla.
- **Re-rank paralelizado** (`ThreadPoolExecutor`) — latencia P50 bajó de ~14,8s a ~5,1s.
- **Re-rank desactivado por defecto** en ambos vademécums — decisión medida, no asumida (ver `rag_subgrafo.py` y `rag_subgrafo_chile.py`).
- **Caché de 15 min en las tools de MINSAL**: latencia bajó de ~11,3s a ~4,8-5,2s en preguntas repetidas.
- **Distinción entre bloqueo real y fallo técnico**: error HTTP honesto (503) en vez de disfrazar una falla de infraestructura como decisión de seguridad.
- **Guardas extendidas a diagnóstico implícito y alergia/contraindicación**.
- **Filtro de similitud mínima de embeddings**: calibrado en 0.4 (Kaggle) y 0.54 (Chile), con evidencia real de falsos positivos descartados.
- **Límite de iteraciones del agente** (`recursion_limit=12`).
- **Dataset de evaluación ampliado a 22 preguntas** (9 informativas + 13 adversarias), con sincronización automática (agregar y actualizar) contra `eval/*.md`.
- **Capa 1 completa: CORS restringido + rate limiting** — evidencia en `docs/evidencia-rate-limiting.md`.
- **Capas 6 y 7 completas: proceso de revisión humana + términos y condiciones**.
- **Capa 2 completa: sesión anónima firmada (JWT)** — con esto, las 7 capas de seguridad mapeadas quedan completas.

## Decisiones de diseño relevantes (ver informe completo para el detalle)

- **Guardrails con texto plano, no `with_structured_output`**: forzar salida JSON estructurada en un prompt de clasificación de seguridad disparó el filtro de moderación del proveedor de forma consistente, incluso con preguntas inocuas.
- **Fail-closed**: si una guarda falla técnicamente, el sistema bloquea por defecto en vez de dejar pasar.
- **Cadenas de modelos de respaldo, independientes para agente y guardas**.
- **RAG del vademécum, 1 fila/ficha = 1 chunk**: en ambas fuentes.
- **Vademécum de Kaggle indexado en inglés**: se traduce solo en la respuesta final.
- **Vademécum chileno como fuente secundaria vía MCP, no primaria**: evita cualquier regresión sobre las preguntas que ya funcionaban con Kaggle.
- **Re-rank como flag, desactivado por defecto**.
- **Autenticación por sesión anónima firmada (JWT), no login real** — razonamiento completo en `docs/por-que-user-id.md`.

## Requisitos previos

- Python 3.11+
- Poetry
- API key de OpenAI (con créditos cargados)
- Cluster de Qdrant Cloud (URL + API key) — cuenta gratuita en [cloud.qdrant.io](https://cloud.qdrant.io)
- (Opcional) Cuenta de Langfuse Cloud y/o LangSmith, para observabilidad
- (Opcional) `vademecum.json` (material de clase del profesor), si quieres usar el vademécum chileno vía MCP

## Setup local

```bash
poetry install --with dev
cp .env.example .env
```

Genera tu `SESSION_SECRET_KEY` (obligatoria, el servidor no arranca sin ella):
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Completa en `.env`: `OPENAI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, y pega el valor generado en `SESSION_SECRET_KEY`. Confirma también `GEN_MODEL` (obligatoria) y, si quieres, `GUARD_MODEL` (opcional). Si vas a usar el vademécum chileno, confirma `MCP_VADEMECUM_CHILE_URL` (por defecto apunta a `localhost:8803`, correcto para desarrollo local).

## Poblar los vademécums en Qdrant (una sola vez cada uno)

El CSV del dataset de Kaggle ya viene incluido en el repo, en `data/vademecum/` — no hace falta descargarlo por separado.

```bash
poetry run python load_vademecum.py
```

El vademécum chileno requiere el `vademecum.json` del profesor en `data/vademecum_chile/vademecum.json` (no se distribuye en este repo — ver "Requisitos previos"):

```bash
poetry run python load_vademecum_chile.py
```

## Correr el servidor

**Si vas a usar el vademécum chileno**, levanta primero el servidor MCP, en su propia terminal:
```bash
poetry run python servidor_vademecum_chile.py
```
Debe quedar corriendo — el backend se conecta a él al arrancar. Sin este paso, el sistema sigue funcionando, solo que sin la fuente secundaria de vademécum (Kaggle sigue funcionando normal).

Luego, en otra terminal, el backend:
```bash
poetry run uvicorn asistente_farmacias.api.main:app --reload --reload-include ".env" --port 8000 --app-dir src
```

Abre **http://localhost:8000/docs** para probar la API directamente.

## Correr el front

**No abras `front/index.html` con doble clic** — algunos navegadores (Safari) y sistemas (macOS, si el proyecto está dentro de Escritorio/Documentos/Descargas) bloquean que una página abierta como archivo local (`file://`) cargue sus propios `.css`/`.js`, y vas a ver la página sin estilos o errores `ERR_ACCESS_DENIED` en la consola. No es un bug del proyecto — es una restricción de seguridad del navegador/sistema operativo.

**Sirve la carpeta con un mini-servidor local** (con el backend ya corriendo en otra terminal, como arriba):

```bash
cd front
python3 -m http.server 5500
```

Y abre en el navegador: http://localhost:5500

Necesitas **las terminales corriendo al mismo tiempo** (servidor MCP en `:8803` si lo usas, backend en `:8000`, front en `:5500`).

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

Pregunta que solo existe en el vademécum chileno (si tienes el servidor MCP corriendo):
```json
{ "pregunta": "¿Para qué sirve el Aartfenacin?" }
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

**Evaluación formal en LangSmith** (sube un dataset + corre un Experimento real, visible en la plataforma con 6 scores por pregunta — `bloqueo_correcto`, `sin_disclaimer_injustificado`, `correctness`, `faithfulness`, `relevance`, `no_recomienda_dosis`):
```bash
poetry run python eval_langsmith.py
```
Si tienes preguntas del vademécum chileno en el dataset, el servidor MCP debe estar corriendo antes de correr el eval.

Revisar en [smith.langchain.com](https://smith.langchain.com) → Datasets & Experiments → `asistente-farmacias-eval`.

Las preguntas de prueba (22 en total: 9 informativas + 13 adversarias) viven en `eval/preguntas_respondibles.md` y `eval/preguntas_no_respondibles.md` — para agregar una pregunta nueva, o cambiar el `tipo`/`esperado` de una existente, solo se edita el `.md`; `eval_langsmith.py` sincroniza automáticamente contra LangSmith (agrega lo nuevo y actualiza lo que cambió), sin duplicar lo que ya estaba subido.

**Elección de `GEN_MODEL`/`GUARD_MODEL`**: para comparar modelos candidatos, corre `eval_langsmith.py` variando `GEN_MODEL` y/o `GUARD_MODEL` por variable de entorno, ej.:
```bash
GUARD_MODEL=gpt-5.6-luna poetry run python eval_langsmith.py
```
El nombre del experimento en LangSmith incluye el modelo evaluado, para poder comparar corridas. Detalle completo de la comparación factorial 3×3 ya realizada, en `docs/eleccion-modelos-gen-guard.md`.

## Chunking del vademécum — estrategia y justificación

1 fila/ficha = 1 chunk, sin splitting, en ambos vademécums. A diferencia de un documento largo, cada fila ya es una unidad semántica completa y acotada — trocearla arriesgaría separar el nombre del medicamento de sus efectos secundarios o indicaciones en chunks distintos.

## Documentación adicional

- `informe-seguridad-privacidad-calidad.md` — informe completo con matriz de 23 riesgos, hallazgos reales del desarrollo, y decisiones de diseño justificadas (incluye la sección de MCP).
- `docs/eleccion-modelos-gen-guard.md` — comparación factorial 3×3 de `GEN_MODEL`/`GUARD_MODEL`, con las 5 matrices de métricas y la decisión final justificada.
- `docs/arquitectura.svg` / `docs/arquitectura-ilustrada.svg` — diagramas de arquitectura (versión técnica y versión ilustrada).
- `docs/flujo-responde-o-no-responde.svg` — árbol de decisión de alto nivel: cuándo el asistente responde y cuándo no.
- `docs/flujo_fallback_vademecum_kaggle_chile.svg` — detalle técnico del fallback Kaggle → verificación LLM → vademécum chileno (MCP), con tiempos reales medidos.
- `docs/capas-seguridad.svg` — diagrama de defensa en profundidad (7 capas, controles implementados).
- `docs/cadena-guard-model.svg` / `docs/cadena-gen-model.svg` — diagramas de las cadenas de fallback de modelos.
- `eval/preguntas_respondibles.md` / `eval/preguntas_no_respondibles.md` — dataset de evaluación, editable sin tocar código.
- `docs/evidencia-rate-limiting.md` — prueba real del rate limiting (mocks + servidor real), con explicación del resultado.
- `terminos-y-condiciones.md` / `front/terminos.html` — términos y condiciones de uso (documento + página integrada al front).
- `docs/proceso-revision-trazas.md` — protocolo de revisión humana periódica de trazas.
- `docs/por-que-user-id.md` — razonamiento de diseño detrás de la autenticación por sesión anónima.
- `docs/flujo-autenticacion.svg` — diagrama del flujo completo (crear sesión, preguntar, renovar token, rechazo de token falsificado).
- `docs/proxy-minsal.md` — por qué las tools de MINSAL pasan por un proxy en Cloud Run Santiago (bloqueo de Cloudflare), y la cadena de resiliencia proxy → snapshot → error.

## Próximos pasos

1. Despliegue del servidor MCP en producción — implica coordinar 2 servicios en Render en vez de 1, con orden de arranque y la variable `MCP_VADEMECUM_CHILE_URL` apuntando a la URL pública real.
2. Política formal de retención/anonimización de trazas — más allá del proceso de revisión ya documentado.

## Entregables de este trabajo

Ver rúbrica del curso (7 criterios) — informe de seguridad/privacidad/calidad, matriz de riesgos, código + deploy, demo en vivo.