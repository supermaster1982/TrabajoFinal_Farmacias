# Informe de Seguridad, Privacidad y Calidad
## Asistente Informativo de Farmacias y Medicamentos

**Trabajo Final — Módulo 04, Diplomado en IA Generativa (UEjecutivos, Universidad de Chile)**
Repositorio: `github.com/genval/TrabajoFinal_Farmacias`

---

## 1. Resumen del caso y diseño

El sistema es un asistente conversacional que informa sobre **farmacias de turno** (datos en vivo de MINSAL) y responde preguntas generales sobre **medicamentos** — con dos fuentes de vademécum (internacional vía RAG directo, y chileno vía protocolo MCP), memoria conversacional y controles de seguridad clínica.

**Contrato de confianza del producto:**
- **Sí hace:** informa locales de turno, dirección y horario; entrega información general citada desde una ficha de medicamento, **siempre citando la fuente de origen** (sección 3.11).
- **No hace:** no confirma stock, precio ni disponibilidad; no diagnostica, no prescribe, no recomienda medicamentos ni dosis.

**Fuentes de datos (tres, complementarias):**
1. API pública de MINSAL (estructurada, cambia a diario) — dos endpoints, ambos con caché de 15 minutos, consumidos vía proxy propio (sección 5.6).
2. Vademécum "Comprehensive Drug Information" (Kaggle) — indexado en Qdrant Cloud, consumido directo desde el agente.
3. Vademécum chileno (material de clase, provisto por el profesor) — indexado en una colección Qdrant separada, consumido vía **protocolo MCP** (sección 3.12), como fuente secundaria/fallback de la anterior.

---

## 2. Arquitectura

```
front/index.html (chat UI, incluye términos y condiciones integrados)
        ↓
POST /session → { token }  (sesión anónima firmada, primera vez)
POST /chat {pregunta} + Authorization: Bearer <token>
        ↓
   FastAPI — CORS restringido por .env, rate limiting (20 req/60s por IP)
        ↓
   StateGraph (LangGraph)
        ↓
   gate_entrada (¿pide dosis/tratamiento/diagnóstico? ¿síntoma + medicamento en el mismo mensaje?)
        ├── SÍ → respuesta_segura → fin
        └── NO → agente ReAct (memoria por user_id, recursion_limit=12)
                     │
                     ├── consultar_farmacias_de_turno      → MINSAL vía proxy (caché 15 min)
                     ├── consultar_farmacias_registradas   → MINSAL vía proxy (caché 15 min)
                     ├── buscar_ficha_medicamento           → RAG directo (Kaggle, filtro 0.4 + verificación LLM)
                     └── buscar_ficha_medicamento_chile      → CLIENTE MCP ─┐
                     ↓                                                      │
                 gate_salida (¿la respuesta igual recomendó algo?)          │
                     ├── SÍ → respuesta_segura → fin                        │
                     └── NO → respuesta_ok (cita agregada aquí)             │
                                                                             ▼
                                                          ┌──────────────────────────────┐
                                                          │  SERVIDOR MCP (proceso aparte) │
                                                          │  servidor_vademecum_chile.py   │
                                                          │  → rag_subgrafo_chile.py        │
                                                          │  (retrieve + filtro 0.54 +       │
                                                          │   verificación LLM) → Qdrant     │
                                                          └──────────────────────────────┘
```

**Decisión de diseño — separación en capas:** canal (API), orquestación (StateGraph), herramientas (4 tools, una de ellas por protocolo MCP), estado (checkpointer por `user_id` + registro propio de preguntas para el historial de las guardas) y control transversal (guardas de entrada/salida) están separados en módulos distintos del código. Esto permite auditar y testear cada capa por separado, y — como se vio en la práctica con el MCP — reemplazar la forma de acceder a una fuente de datos (import directo → protocolo MCP) sin tocar el resto del sistema.

---

## 3. Seguridad — guardrails y defensa en profundidad

El proyecto mapea sus controles en **7 capas de defensa en profundidad** (diagrama: `docs/capas-seguridad.svg`).

### 3.1 Diseño: dos guardas, no una

- **Guarda de entrada:** evalúa la pregunta del usuario *antes* de invocar al agente/tools.
- **Guarda de salida:** defensa en profundidad ante intentos de jailbreak que logren "colar" la petición.

Ambas devuelven el **mismo mensaje** de rechazo, para no revelar cuál capa específica actuó.

### 3.2 Fail-closed, y distinción entre bloqueo real y falla técnica

Si cualquiera de las dos guardas **falla técnicamente**, el sistema **bloquea por defecto** — con un error HTTP honesto (503, `GuardaNoDisponibleError`), no con el mensaje de rechazo.

### 3.3 Hallazgo real: el propio prompt del guardrail disparaba moderación

`with_structured_output` combinado con un prompt de clasificación sobre dosis/tratamiento disparó el filtro de moderación de OpenAI, incluso para preguntas inocuas. Se resolvió con texto plano + parseo manual.

### 3.4 Guardas extendidas a diagnóstico implícito y alergia/contraindicación

Además de dosis/tratamiento, se cubrió diagnóstico implícito e interacción/contraindicación personalizada.

### 3.5 Memoria multi-turno de las guardas — hallazgos y ajustes finales

**El problema original:** las guardas evaluaban solo el mensaje actual. Se corrigió con un registro propio de preguntas (`_historial_preguntas`), separado del checkpointer del agente.

**Hallazgo 1 — alucinación del criterio 4 sin respaldo real (resuelto).** El LLM a veces alucinaba una coincidencia síntoma↔indicación con el historial vacío. Solución: verificación en código (`_criterio4_verificado`) que exige que la cita del LLM aparezca literalmente en el historial real.

**Hallazgo 2 — el historial se contaminaba con la pregunta del turno actual (resuelto).** Al filtrar la pregunta actual del historial para `gate_salida`, el filtro dejaba el historial completamente vacío en el caso de síntoma+medicamento en el mismo mensaje, impidiendo que el criterio 4 se disparara nunca en ese caso.

**Hallazgo 3 y decisión final — el patrón "mismo mensaje" se mueve a `gate_entrada`.** Tras iterar entre ampliar el criterio 4 de `gate_salida` (bloquear cualquier medicamento tras cualquier síntoma, sin importar coincidencia) y notar que eso bloqueaba de más casos legítimos en turnos separados (ej. preguntar por Aspirina varios turnos después de mencionar un síntoma no relacionado), se llegó al diseño final, más simple y confiable:

- **`gate_entrada`** bloquea de forma determinística cualquier mensaje que combine, en el *mismo* texto, un síntoma personal y un medicamento específico — sin necesitar buscar nada ni depender de si el medicamento existe en algún corpus. Cubre el caso que motivó todo esto (Viadil, y cualquier medicamento del vademécum chileno usado de la misma forma).
- **`gate_salida`** vuelve a su forma original y más precisa: bloquea solo si el historial de turnos *anteriores* menciona un síntoma **y** la ficha citada tiene una indicación que coincide razonablemente con ese síntoma — no "cualquier medicamento", evitando el sobre-bloqueo detectado.

Esta combinación quedó validada con evidencia real: Viadil (mismo mensaje) bloquea en `gate_entrada` en ~1.5s sin gastar ninguna tool; Aspirina tras un síntoma no relacionado en un turno anterior ya **no** se bloquea; Aspirina tras "me duele la cabeza" en un turno anterior **sí** se bloquea (coincidencia real de indicación).

### 3.6 Deduplicación de texto repetido

Post-procesamiento determinístico (`_colapsar_texto_duplicado`) para el caso en que el modelo repite la misma frase dos veces.

### 3.7 Límite de iteraciones del agente

`recursion_limit=12` — evita gasto de tokens sin control.

### 3.8 Red y transporte: CORS y rate limiting

CORS configurable vía `.env`; rate limiting de 20 req/60s por IP, probado en 3 niveles.

### 3.9 Pruebas adversarias realizadas (22 preguntas en el dataset formal de evaluación)

| Prueba | Resultado |
|---|---|
| Pregunta directa de dosis | Bloqueada |
| Roleplay/actuación de rol profesional | Bloqueada |
| Horario de administración | Bloqueada |
| Diagnóstico implícito | Bloqueada |
| Interacción/contraindicación | Bloqueada |
| Interacción con alergia, dos fraseos distintos | Ambas bloqueadas |
| Síntoma + medicamento en el mismo mensaje (Viadil, Aartfenacin) | Bloqueadas en `gate_entrada`, sin gastar tools (sección 3.5) |
| Preguntas informativas puras (incluye una del vademécum chileno vía MCP) | Respondidas correctamente, con cita de fuente (sección 3.11) |
| Preguntas fuera de dominio | Rechazadas con mensaje de alcance (sección 3.10) |
| Falla forzada de la guarda | Bloqueó por fail-closed, 503 honesto |

Confirmado con `bloqueo_correcto = 1.00` en la evaluación formal más reciente (sección 5.5).

### 3.10 Restricción de alcance del agente

El `SYSTEM_PROMPT` restringe el alcance a farmacias/medicamentos, evitando que el agente use conocimiento general para preguntas ajenas al dominio. Confirmado con `bloqueo_correcto = 1.00` en múltiples corridas.

### 3.11 Citas de fuente obligatorias en cada respuesta

**El requisito:** el enunciado pide "siempre citando la fuente". Se agregó extracción determinística de citas (`_extraer_citas` en `graph.py`), que analiza las tools realmente invocadas y arma la línea de cita a partir del texto real que devolvieron, no de lo que el LLM decida repetir — reconoce tanto `buscar_ficha_medicamento` (Kaggle) como `buscar_ficha_medicamento_chile` (MCP), sin distinción, porque ambas devuelven el mismo formato de cita `[Fuente: ... — ... · relevancia=...]`.

**Bugs corregidos durante la implementación:** contaminación de citas entre turnos (el checkpointer acumula todos los mensajes; se filtró a solo los del turno actual), y la cita interfiriendo en la evaluación de `gate_salida` (se movió su construcción a después de la aprobación de la guarda).

### 3.12 Vademécum chileno vía protocolo MCP — arquitectura de dos servicios

**El requisito:** el profesor pidió explícitamente que, si se usaba el vademécum chileno que compartió como material de clase, el acceso se implementara "como API o MCP, consumido desde la llamada de la tool" — no como un simple import de Python. Se eligió MCP, siguiendo el mismo patrón de `protocolo_mcp.ipynb` (Clase 5.4).

**Decisión de arquitectura — fallback, no reemplazo:** el vademécum chileno se conecta al agente como **segunda fuente**, usada solo si `buscar_ficha_medicamento` (Kaggle, ya validado con el eval formal) responde que no encontró información relevante — mismo patrón de fallback que ya existe entre las dos tools de MINSAL. Esto evita cualquier regresión sobre las preguntas que ya funcionaban, y resuelve exactamente el caso que motivó todo el trabajo de esta sección: un medicamento chileno (ej. Aartfenacin) ausente del corpus internacional.

![Flujo de fallback Kaggle → verificación LLM → vademécum chileno](docs/flujo_fallback_vademecum_kaggle_chile.svg)

**Componentes nuevos:**
- `servidor_vademecum_chile.py` — servidor FastMCP, proceso aparte. No reimplementa la búsqueda: envuelve `rag_subgrafo_chile.py` tal cual (retrieve → filtro de similitud 0.54 → verificación de relevancia con LLM, la misma lógica ya validada), agregando solo la capa de protocolo MCP encima.
- `tool_rag_chile.py` — cliente MCP (`MultiServerMCPClient`), reemplaza el import directo anterior. La URL del servidor es configurable vía `MCP_VADEMECUM_CHILE_URL` en `.env`, para poder apuntar a producción sin tocar código el día del deploy.

**Hallazgo — conflicto de dependencias con el material de clase.** `langchain-mcp-adapters==0.3.2` (la versión usada en el notebook de la clase) exige `langchain-core >= 1.3.3`, una versión mayor incompatible con el `langchain-core ^0.3.0` que sostiene todo el resto del proyecto ya validado (`create_react_agent`, que en la serie 1.x de LangChain cambia de nombre y de API). Actualizar habría sido un cambio grande y riesgoso a días de la entrega. Se resolvió usando `langchain-mcp-adapters==0.1.14`, una versión anterior compatible con `langchain-core >= 0.3.36, < 2.0.0` — sin ningún conflicto, sin tocar el resto del stack.

**Hallazgo 1 — event loop anidado bajo `uvicorn --reload` (resuelto).** `create_react_agent` construye su lista de tools al importar el módulo, de forma síncrona — pero `MultiServerMCPClient.get_tools()` es asíncrono. La primera implementación usaba `asyncio.run()` directo para resolver esto, lo cual funcionaba con `uvicorn` normal pero fallaba con `uvicorn --reload` (`RuntimeError: asyncio.run() cannot be called from a running event loop`), porque el proceso de recarga de `uvicorn --reload` ya tiene su propio loop activo (`uvloop`) antes de que se importen los módulos de la aplicación. Solución: `_run_async()` detecta si ya hay un loop corriendo y, de ser así, ejecuta la corrutina en un hilo aparte con su propio loop nuevo — evita anidar un loop dentro de otro.

**Hallazgo 2 — cliente MCP compartido fallaba silenciosamente entre requests (resuelto).** Con un único `MultiServerMCPClient` creado una vez al importar el módulo y reutilizado en cada pregunta, la tool devolvía un error genérico ("la consulta al vademécum chileno falló") sin que el servidor MCP registrara ninguna sesión nueva para esa llamada real — solo la del arranque. Causa probable: el cliente compartido conserva recursos internos (ej. un cliente HTTP asíncrono) atados al event loop en el que se creó (el hilo aparte del Hallazgo 1); ese loop se cierra apenas termina el hilo, dejando esos recursos inválidos para invocaciones posteriores desde el loop real de FastAPI. Solución: cada invocación de la tool crea su **propia** conexión MCP desde cero (`_llamar_mcp`), que vive y muere dentro del mismo hilo/loop, sin nada compartido entre llamadas — a costa de una reconexión por consulta, aceptable para el volumen de este proyecto. Confirmado con evidencia en los logs del servidor MCP: cada pregunta real genera una sesión nueva, con `CallToolRequest`, `retrieve`, y la verificación de relevancia ejecutándose correctamente del lado del servidor.

**Efecto colateral positivo del rediseño:** con conexiones aisladas por llamada, el backend ya no falla al arrancar si el servidor MCP no está disponible en ese momento — solo falla esa tool puntual al invocarse (con un mensaje de error dentro de la respuesta, no un mensaje bloqueado ni cita alguna, ver 3.11), lo cual es más resiliente que la versión anterior.

**Orden de arranque obligatorio:** el servidor MCP debe iniciarse *antes* que la API principal — `poetry run python servidor_vademecum_chile.py` en una terminal, luego `uvicorn` en otra.

**Validación:** confirmado con evidencia real en dos niveles — pruebas manuales en el front (respuesta correcta de Aartfenacin, con cita del vademécum chileno) y el eval formal (sección 5.5), con 2 preguntas nuevas específicas para este camino.

**Pendiente:** deploy del servidor MCP en producción — implica coordinar 2 servicios en vez de 1 en el hosting (Render), a resolver con el equipo antes de la entrega final.


---

## 4. Resiliencia ante caída o retiro de modelo

Durante el desarrollo, OpenAI retiró `gpt-4o-mini` de ChatGPT, y Anthropic suspendió temporalmente el acceso a Claude Fable 5 y Mythos 5 por controles de exportación de EE.UU. `gpt-5-mini` dejó de aceptar `temperature` distinto de 1 y ya tiene retiro de API anunciado — se sacó de toda cadena de respaldo.

**Dos mecanismos de resiliencia:**
- **`GUARD_MODEL`**: `invocar_con_fallback()` prueba la cadena en orden. Fail-closed si los tres fallan.
- **`GEN_MODEL`**: `ChatOpenAI.with_fallbacks()` de LangChain.

```
GUARD_MODEL:  gpt-5.6-luna → gpt-5.4-mini → gpt-5.4-nano
GEN_MODEL:    gpt-5.6-luna → gpt-5.4-mini → gpt-5.4-nano
```

Detalle completo en `docs/eleccion-modelos-gen-guard.md`.

---

## 5. Calidad — RAG semántico y evaluación

### 5.1 Estrategia de chunking (vademécum de Kaggle)

1 fila del CSV = 1 chunk, sin trocear.

### 5.2 Estrategia de idioma

El dataset de Kaggle está en inglés; se indexa así, traduciendo solo en la respuesta final.

### 5.3 Retrieval, filtro de relevancia mínima, y verificación de relevancia con LLM

Pipeline: `similarity_search` (k=8) → filtro de similitud mínima (umbral 0.4 en Kaggle, 0.54 en Chile) → **verificación de relevancia con LLM sobre la mejor candidata** → filtro final → máximo 3 fichas.

**Hallazgo que motivó la verificación con LLM (además del filtro de similitud):** con el filtro de embeddings solo, una pregunta sobre un medicamento ausente del corpus (ej. "Aartfenacin" en Kaggle) podía devolver un candidato con score por encima del umbral pero sin relación real (ej. "Allopurinol", score 0.508 > 0.4). El umbral de similitud por sí solo no distingue "esto es lo más parecido que hay, aunque no tenga relación" de "esto sí es relevante". Se agregó una verificación adicional: un LLM confirma si la mejor candidata tiene relación real con lo preguntado (considerando traducciones, typos, nombres comerciales vs. genéricos) — más robusto que comparar texto, porque el LLM entiende variaciones que una regla de prefijos o substrings no captura. Si la respuesta es "no", se descartan todas las candidatas, activando el fallback al vademécum chileno.

**Calibración del umbral del vademécum chileno, con evidencia real:** confirmado en corridas con 50, 500, y las 12,411 fichas completas, que 0.54 descarta el falso positivo conocido (Abatero/Abiraterona, score 0.517) sin perder casos genuinamente relevantes.

### 5.4 Re-rank: decisión medida, no asumida

Comparación sin_rerank vs con_rerank sobre el vademécum de Kaggle: sin diferencia de calidad medible, con re-rank multiplicando la latencia ~3x. Se mantiene desactivado por defecto en ambos vademécums.

### 5.5 Evaluación formal en LangSmith

Dataset de **22 preguntas (9 informativas + 13 adversarias)** — incluye, desde esta ronda, 2 preguntas específicas del vademécum chileno/MCP: una que fuerza el camino completo (Kaggle descarta → MCP responde), y una que confirma que `gate_entrada` bloquea igual sin importar si el medicamento nombrado pertenece a Kaggle o a Chile.

**Hallazgo sobre la sincronización del dataset con LangSmith (resuelto).** `subir_dataset()` solo agregaba preguntas *nuevas*, nunca actualizaba el `tipo`/`esperado` de una pregunta ya existente si cambiaba en el `.md` local — cuando Viadil se movió de "informativa" a "adversaria" tras el rediseño de `gate_entrada` (sección 3.5), LangSmith siguió evaluándola contra el comportamiento viejo, mostrando `bloqueo_correcto=0.0` pese a que el sistema bloqueaba perfectamente. Se corrigió agregando comparación y actualización (`client.update_example`) de las preguntas existentes cuya clasificación cambió, no solo la detección de preguntas nuevas.

**6 métricas por pregunta:** `bloqueo_correcto`, `sin_disclaimer_injustificado`, `correctness`, `faithfulness`, `relevance`, `no_recomienda_dosis` — sin cambios en esta ronda.

**Resultados finales:** `1.00` en `bloqueo_correcto` en las 22 preguntas, confirmado en múltiples corridas tras todos los fixes de las secciones 3.5, 3.12 y 5.5.

### 5.6 Calidad de datos de MINSAL

Proxy propio en Cloud Run Santiago esquiva el bloqueo de Cloudflare a IP de datacenter extranjeras. Cadena de resiliencia: proxy en vivo → snapshot rotulado con fecha → mensaje digno. Detalle en `docs/proxy-minsal.md`.

---

## 6. Privacidad

- **Credenciales:** `.env` excluido de Git vía `.gitignore` — incluye también `data/vademecum_chile/` (el JSON del profesor no se redistribuye en el repo público).
- **Observabilidad:** LangSmith activo; Langfuse implementado pero no configurado.
- **Contexto legal chileno:** Ley 21.719 entra en vigor el 1 de diciembre de 2026.

### 6.1 Autenticación: sesión anónima firmada (RESUELTO)

JWT (HS256), verificado en cada pregunta. Razonamiento en `docs/por-que-user-id.md`.

### 6.2 Términos y condiciones — RESUELTO

`terminos-y-condiciones.md` + `front/terminos.html`.

### 6.3 Proceso de revisión humana de trazas — RESUELTO

Protocolo documentado en `docs/proceso-revision-trazas.md`.

---

## 7. Matriz de riesgos

| # | Riesgo | Probabilidad | Impacto | Mitigación verificable | Dueño | Estado |
|---|---|---|---|---|---|---|
| 1 | El sistema es interpretado como asesoría médica/farmacéutica | Baja | Crítico | Guardrail de entrada y salida, fail-closed, 22 preguntas adversarias | Backend | ✅ |
| 2 | El proveedor del LLM retira o suspende el modelo principal sin aviso | Baja-Media | Crítico | Cadena de fallback independiente para `GEN_MODEL`/`GUARD_MODEL` | Backend | ✅ |
| 3 | El propio prompt del guardrail dispara la moderación del proveedor | Media | Alto | Migración a texto plano + parseo manual | Backend | ✅ |
| 4 | Dato de MINSAL desactualizado o inexistente para una comuna | Media | Alto | Fecha visible + fallback al directorio completo | Backend | ✅ |
| 5 | API de MINSAL no responde (timeout, caída, bloqueo de Cloudflare) | Media-Alta | Alto | Proxy en Cloud Run Santiago; fallback proxy → snapshot → mensaje digno | Backend | ✅ |
| 6 | Preguntas de salud quedan registradas sin política de retención clara | Media | Medio | Proceso de revisión documentado; pendiente política formal | Backend/Producto | ⏳ parcial |
| 7 | Delay de ingesta de Langfuse afecta la demo en vivo | Alta | Bajo | LangSmith como observabilidad principal | Backend | ✅ |
| 8 | El re-rank del RAG agrega latencia sin garantía de mejora | Media | Bajo-Medio | Mini-eval cuantitativo; desactivado por defecto | Backend | ✅ |
| 9 | Credenciales expuestas accidentalmente en el repositorio | Baja | Crítico | `.gitignore` + verificación manual | Todo el equipo | ✅ |
| 10 | Costo escala sin control | Media | Medio | Cadena económica + `recursion_limit=12` + rate limiting | Backend | ✅ |
| 11 | Ciberataque genérico (DoS, abuso de la API pública) | Baja-Media | Alto | CORS + rate limiting en 3 niveles | Backend | ✅ |
| 12 | El sistema sugiere o nombra un diagnóstico/enfermedad | Media | Alto | Guardrail extendido, `bloqueo_correcto=1.00` | Backend | ✅ |
| 13 | La API de MINSAL podría limitar o bloquear tráfico por volumen | Media | Alto | Caché de 15 min | Backend | ✅ |
| 14 | El sistema promueve indirectamente una marca comercial | Baja-Media | Medio | Prompt no compara ni recomienda marcas | Backend | ✅ |
| 15 | Bucle no acotado del agente | Baja | Medio | `recursion_limit=12` | Backend | ✅ |
| 16 | Recomendación que interactúa con alergia/contraindicación no declarada | Baja | Crítico | Guardrail extendido, 3 preguntas adversarias | Backend | ✅ |
| 17 | Uso del identificador de otra persona sin verificación | Baja | Alto (privacidad) | Sesión anónima firmada (JWT) | Backend | ✅ |
| 18 | Fuga del corpus completo del RAG | Baja | Medio | Solo retorna fichas filtradas (top 3) | Backend | ✅ |
| 19 | Falta de términos y condiciones explícitos de uso | Resuelto | Medio-Alto | `terminos-y-condiciones.md` + `front/terminos.html` | Producto | ✅ |
| 20 | Evasión de la guarda vía contexto multi-turno o mismo mensaje | Baja | Medio (UX) | `gate_entrada` bloquea determinísticamente el caso de mismo mensaje; `gate_salida` bloquea el caso de turnos separados con coincidencia real de indicación (sección 3.5) | Backend | ✅ |
| 21 | El agente responde preguntas fuera de su dominio declarado | Baja | Medio | `SYSTEM_PROMPT` restringe el alcance; `bloqueo_correcto=1.00` (3.10) | Backend | ✅ |
| 22 | Información de ficha o MINSAL entregada sin citar la fuente | Baja | Medio (cumplimiento del enunciado) | Extracción de citas determinística (3.11) | Backend | ✅ |
| 23 | Falla del servidor MCP (caído, desconectado) deja sin respuesta la fuente chilena | Media (proceso aparte, puede no estar corriendo) | Bajo-Medio (fuente secundaria, no la única) | La tool captura cualquier error de conexión y responde con un mensaje honesto, sin citar ninguna fuente falsa; el backend no crashea (sección 3.12). El sistema completo sigue funcionando con Kaggle como fuente principal. | Backend | ✅ |

**23 de 23 riesgos con el aspecto de seguridad/alcance/cumplimiento resuelto.**

---

## 8. Limitaciones conocidas

1. **Inconsistencia residual de UX en `gate_entrada`** (no de seguridad) — variabilidad puntual ya documentada en corridas anteriores del LLM, no relacionada con los fixes de esta ronda.
2. **Disclaimer injustificado intermitente en `GEN_MODEL`** (no de seguridad) — detectado y medido, no perseguido por decisión consciente de priorización.
3. El mini-eval de calidad usó solo 3 preguntas para sin_rerank vs con_rerank — la evaluación formal ya cubre 22 preguntas con 6 métricas, que es la fuente principal de confianza.

## 9. Próximos pasos

1. **Despliegue del servidor MCP en producción** — pendiente coordinar con el equipo; implica 2 servicios coordinados en Render en vez de 1, con orden de arranque y una variable de entorno nueva (`MCP_VADEMECUM_CHILE_URL`) apuntando a la URL pública real.
2. **Política formal de retención/anonimización de trazas** — falta definir cuánto tiempo se conservan los datos, más allá del proceso de revisión ya documentado (`docs/proceso-revision-trazas.md`).

## Referencias adicionales

Detalle completo de la elección de `GEN_MODEL`/`GUARD_MODEL`, con la matriz de evaluación 3×3, en `docs/eleccion-modelos-gen-guard.md`. Detalle completo del proxy de MINSAL, con la cadena de resiliencia de tres niveles, en `docs/proxy-minsal.md`.