# Trabajo Final — Módulo 04: Resumen completo del enunciado

Diplomado de Extensión en IA Generativa para Organizaciones — UEjecutivos, Universidad de Chile, Facultad de Economía y Negocios (FEN).
**Profesor:** José Gregorio Argomedo — gargomedo@gmail.com
**Módulo 04:** Calidad, Seguridad e Infraestructura en Aplicaciones de IA Generativa
**Modalidad:** Trabajo grupal · Demo en vivo · Puntaje técnico del proyecto: 0–7
**Importante:** 0–7 es el puntaje técnico del proyecto, NO una nota chilena automática — la conversión a nota final la hace el equipo docente.

---

## Índice del enunciado (5 pasos, 18 paneles)

1. Caso de negocio
2. Qué construir (arquitectura, stack, 3 flujos de prueba)
3. Entregables y demo
4. Rúbrica (7 puntos)
5. Recursos y datos

---

## Paso 1 — Caso de negocio

### La necesidad
Fuera del horario hábil, una persona necesita saber **qué farmacia está abierta** y entender una **ficha de medicamento** que ya tiene indicada. La solución conecta:
- Una **fuente estructurada que cambia a diario** — la API de farmacias de MINSAL.
- Una **fuente documental para RAG** — un vademécum.
- Mediante una **interfaz conversacional**.

### Contrato de confianza — "El asistente informa; no trata"
| Sí hace | No hace |
|---|---|
| Locales de turno, dirección y horario | Stock, precio o disponibilidad del medicamento |
| Información general citada desde una ficha | Diagnóstico o prescripción; no recomienda medicamentos ni dosis |

**Frontera clínica (textual):** *"El asistente no recomienda medicamentos ni dosis; rechaza y deriva a profesionales de salud. Tampoco diagnostica ni prescribe."*

### Viaje del usuario — 4 momentos
1. **Contexto** — Necesita orientación: busca una farmacia abierta o explicación general de una ficha.
2. **Turno** — Consulta MINSAL: la app filtra registros vigentes por comuna y devuelve local, dirección y horario.
3. **Ficha** — Recupera evidencia: el RAG busca en el vademécum y cita el medicamento/registro recuperado.
4. **Guardrail** — Ayuda sin recomendar: si piden tratamiento o dosis, rechaza, deriva y ofrece información permitida.

> Los tres flujos (turno, RAG, guardrail) validan el **núcleo funcional**; deploy, resiliencia, informe y matriz completan la entrega.

### Farmacias es un ejemplo — se puede cambiar de proyecto
Es aceptado un proyecto personal/otro problema si demuestra capacidades **equivalentes**:
- Dos fuentes de datos complementarias
- Búsqueda o recuperación con evidencia
- Orquestación e historial
- Controles de seguridad
- API, interfaz y despliegue

Se evalúa con la **misma rúbrica** y los mismos entregables, sea cual sea el tema elegido.

**Recomendación (no requisito):** compartir temprano con el profesor necesidad, usuarios, datos y controles, para detectar brechas. **Evitar datos personales o sensibles reales.**

### Test de viabilidad (6 condiciones, autoevaluación)
- [ ] Problema real y usuarios identificables
- [ ] Dos fuentes de datos complementarias
- [ ] Búsqueda o recuperación con evidencia
- [ ] Orquestación e historial demostrables
- [ ] Controles de seguridad concretos y testeables
- [ ] API, interfaz y despliegue operativos

---

## Paso 2 — Qué construir

### Arquitectura de referencia — "Un sistema, cuatro responsabilidades"
La arquitectura separa: **canal, API, orquestación, herramientas, estado y controles.** Esta separación debe verse tanto en el código como en la explicación.

```
Front conversacional ──┐
FastAPI / LangServe ────┼──→ LangGraph (routing + estado) ──→ Tool MINSAL (turnos en vivo)
                                                          └──→ Tool RAG (vademécum citado)

Estado: historial por user_id ─┐
Control transversal: validación + derivación ─┘  (ambos, transversales al flujo)
```

### Stack obligatorio — tabla con evidencia y punto de rúbrica

| Pieza | Conducta observable | Evidencia mínima | Punto rúbrica |
|---|---|---|---|
| LangGraph | Routing real entre herramientas y estado | Grafo o agente + explicación de decisiones | 2 |
| Historial | Dos turnos dependientes por `user_id` | Checkpointer, store o BD en la app | 2 / 6 |
| RAG semántico | Retrieval por embeddings, no filtro de texto | Vector store + ficha citada | 3 |
| MINSAL en vivo | Consulta turnos al responder | Tool + timeout + error digno | 4 |
| Guardrails | Rechaza tratamiento y deriva | Control activo + pruebas adversarias | 5 |
| API + front + cloud | `POST {user_id, pregunta}` disponible | URL desplegada y front que la consume | 6 |

**Nota sobre API:** FastAPI es la ruta recomendada; LangServe sigue aceptado según el programa original. **El despliegue debe estar en un entorno cloud — `localhost` NO acredita el punto de deploy.**

### Los tres flujos de prueba (la "prueba de fuego" de la demo)
1. **Turnos + historial** — valida datos en vivo + 2 turnos dependientes.
2. **RAG + fuente** — ficha recuperada con cita visible.
3. **Rechazo + derivación** — intento adversario, rechazo y derivación.

> "La demo prueba decisiones, no prompts sueltos." Estos 3 flujos validan el núcleo funcional; evidencia escrita y operativa completan la entrega.

---

## Paso 3 — Entregables y demo

### Los 4 entregables (pipeline)
1. **Informe** — Seguridad, privacidad y calidad: controles por capa, datos que se guardan, método de evaluación.
2. **Matriz de riesgos** — Riesgo, probabilidad, impacto, mitigación verificable, dueño responsable.
3. **Código + deploy** — Repositorio/paquete de código, API y front accesibles en una **URL cloud**.
4. **Demo en vivo** — Caso → arquitectura → tres flujos → riesgos. El sistema responde contra el entorno **desplegado**, no localhost.

**Apoyo (material de otras clases del módulo):** defensa en profundidad · riesgos GenAI · gobernanza responsible AI.

### Guion recomendado de la demo — 6 escenas
1. **Caso** — Necesidad, usuarios, fuentes y trade-offs.
2. **Arquitectura** — Grafo, tools, memoria y controles.
3. **Turnos** — Comuna y segundo turno dependiente.
4. **RAG** — Ficha recuperada y cita visible.
5. **Guardrail** — Intento adversario, rechazo y derivación.
6. **Operación** — Dos riesgos críticos y sus mitigaciones.

> Presentar contra la **URL desplegada**. Si MINSAL falla en vivo durante la demo: mostrar timeout, mensaje digno y fallback documentado (no ocultarlo, es parte de la evidencia de calidad).

### Logística (avisos importantes)
- **Fecha, canal de entrega y duración por grupo:** se publican por el canal oficial del curso — *"No usen esta presentación como calendario."* (la fecha en el material puede estar desactualizada)
- **Responsabilidad grupal:** la evaluación es grupal y **cualquier integrante debe poder explicar cualquier parte** del proyecto. Revisar la composición de equipos (archivo aparte del curso).

### Checklist "pre-flight" antes de presentar (8 ítems)
- [ ] La URL cloud responde; no depende de localhost
- [ ] Dos turnos dependientes conservan el contexto
- [ ] El guardrail resiste pregunta directa, insistencia y roleplay
- [ ] El RAG cita la ficha o registro recuperado
- [ ] MINSAL se consulta en vivo y existe fallback documentado
- [ ] Informe de seguridad, privacidad y calidad listo
- [ ] Matriz con mitigaciones verificables y dueños
- [ ] Todos pueden explicar grafo, datos, controles y deploy

---

## Paso 4 — Rúbrica (7 criterios, 1 punto cada uno)

| # | Criterio | Descripción |
|---|---|---|
| 1 | Caso y diseño | Problema, necesidad, datos, decisiones, alternativas y trade-offs justificados |
| 2 | LangGraph + historial | Grafo con routing y estado; memoria multi-turno por `user_id` |
| 3 | RAG semántico | Embeddings + vector store; respuesta basada en retrieval y ficha citada |
| 4 | MINSAL en vivo | Tool usa turnos reales y maneja timeout, latencia o caída |
| 5 | Seguridad, privacidad y calidad | Guardrail probado, informe completo y matriz de riesgos accionable |
| 6 | API + front + cloud | Contrato con historial, UI que consume la API y URL desplegada |
| 7 | End-to-end + demo | Tres flujos estables y cualquier integrante explica el sistema |

**Fuente de verdad canónica:** `data/tareas-m04/eval-prompt-trabajo-final.md` (archivo del repo del curso, no en este resumen — consultarlo directo si hay dudas de formato de evaluación).

### Mapa de trazabilidad (3 pilares → 7 criterios)
- **Caso de negocio** → Criterio 1 (Problema y diseño justificado)
- **Funcionamiento y operación** → Criterio 5 (Seguridad/privacidad/calidad) + Criterio 7 (Estabilidad end-to-end y demo)
- **Herramientas obligatorias** → Criterio 2 (LangGraph+historial) + Criterio 3 (RAG) + Criterio 4 (Datos externos en vivo) + Criterio 6 (API+front+cloud)

### ⚠️ Criterio 5 — CONDICIÓN DURA (la más importante de recordar)
> **"El bonus puede compensar puntaje faltante dentro del tope 7, pero NO cambia el estado del criterio 5: si el sistema recomienda medicamentos o dosis, ese criterio queda NO LOGRADO."** — sin excepción, sin importar qué tan bien esté el resto del proyecto.

**Respuesta segura (ejemplo dado por el profesor):**
> *"No puedo recomendarte un medicamento ni una dosis; eso requiere evaluación profesional. Sí puedo ayudarte a encontrar una farmacia de turno o explicar una ficha que ya te hayan indicado."*
- ✓ Rechaza recomendación y dosis
- ✓ Deriva a un profesional de salud
- ✓ Ofrece una acción permitida y útil

**Respuesta insegura (ejemplo de lo que NO hay que hacer):**
> *"Para el dolor de cabeza toma ibuprofeno 400 mg cada 8 horas; si persiste, aumenta la dosis."*
- ✕ Diagnostica de facto y recomienda dosis
- ✕ Sin evaluación profesional ni derivación
- ✕ El punto 5 no se otorga

### Ejemplos de riesgos bien formulados (tabla del profesor)
| Riesgo | Prob. | Impacto | Mitigación verificable | Dueño |
|---|---|---|---|---|
| El asistente inventa una dosis | Media | Crítico | Guardrail entrada/salida + RAG citado + 20 pruebas adversarias en CI | Backend |
| API MINSAL no responde | Media | Alto | Timeout 5s + cache 15 min + fallback rotulado + mensaje digno | Backend |

**Ejemplo de riesgo DÉBIL (a evitar):** *"La IA puede equivocarse; mitigación: tener cuidado."* — Le falta probabilidad, impacto, control verificable y dueño.

### Bonus (dentro del tope de 7, no lo supera)
Se acepta como evidencia extra: observabilidad/evals, red teaming, seguridad extra, streaming, cache/resiliencia, UI pulida, o más fuentes públicas. **Debe existir evidencia real, no solo una mención** en el informe.

---

## Paso 5 — Recursos y datos

### Fuente estructurada — API MINSAL (2 endpoints públicos, sin API key)
1. **`getLocales.php`** — Directorio completo de locales informado por MINSAL (estén o no de turno).
   `https://midas.minsal.cl/farmacia_v2/WS/getLocales.php`
2. **`getLocalesTurnos.php`** — Locales de turno (solo los abiertos ahora).
   `https://midas.minsal.cl/farmacia_v2/WS/getLocalesTurnos.php`

**Requisito explícito:** el sistema debe **consultar los turnos en vivo** al responder — agregar timeout, cache corto y fallback rotulado.

**Alcance de datos:** MINSAL informa locales y turnos. **No confirma stock, precio ni disponibilidad** de un medicamento.

**Muestra capturada de referencia:** 13 comunas seleccionadas, capturada el 2026-07-14 desde 301 registros observados. *"Algunas filas traen fechas anteriores; no representa el estado actual"* (advertencia explícita del profesor sobre calidad de los datos).

### Flujo de calidad de datos MINSAL (5 pasos obligatorios)
La tool **no debe pasar el JSON crudo al LLM** — cada transformación protege una afirmación:
1. **Recibir** — Timeout + esquema: verifica HTTP, JSON y campos mínimos antes de continuar.
2. **Normalizar** — Texto y teléfonos: aplica `strip()`, colapsa espacios, marca datos vacíos.
3. **Filtrar** — Fecha y comuna: descarta registros viejos; **`fk_region` es id interno, NO la región oficial** (no usarlo como tal).
4. **Interpretar** — Turnos nocturnos: apertura 09:00 y cierre 08:59 significa que **cierra al día siguiente**.
5. **Responder** — Dato + límite: devuelve local, dirección y horario; **nunca infiere stock o precio**.

**Fallback permitido:** snapshot documentado con fecha visible. **No puede presentarse como dato en vivo** si no lo es.

### Fuente documental para RAG
**Dataset sugerido:** ["Comprehensive Drug Information"](https://www.kaggle.com/datasets/anoopjohny/comprehensive-drug-information-dataset) (Kaggle) — corpus **educativo**, en inglés.
> *"Definan versión, esquema, traducción y chunking. No es una fuente clínica autoritativa ni habilita recomendaciones."*

**Bonus posible:** más fuentes públicas (ISP, datos abiertos MINSAL, u otras documentadas). Citar origen, fecha, licencia y límites — **no mezclar autoridad clínica con disponibilidad comercial.**

### Material de apoyo ya visto en el diplomado (enlaces del curso)
- M04 · Seguridad — `Notebook_01_Ejercicio_Seguridad_Resultado.ipynb` (guardrails y validación)
- M03 · Vector stores — `Notebook_03_Index_&_Vector_Stores.ipynb` (indexado y búsqueda)
- M03 · Multi-RAG — `Notebook_06_Multi_RAG_Agent.py` (LangGraph + tools)
- M04 · Defensa en profundidad — deck de controles por capa

---

## Resumen ejecutivo — lo que NO hay que olvidar

1. **Condición dura:** criterio 5 se pierde por completo si el sistema recomienda dosis/tratamiento, sin importar el resto.
2. **`localhost` no acredita deploy** — tiene que estar en la nube para el punto 6.
3. **`fk_region` de MINSAL es un ID interno**, no la región real — no confundir en la lógica de filtrado.
4. **Turno nocturno:** 09:00→08:59 = cierra al día siguiente, no hay que asumir que "08:59" significa que cerró temprano.
5. El dataset de Kaggle **no es fuente clínica autoritativa** — solo para practicar embeddings/retrieval/citas.
6. La responsabilidad de la demo es **grupal** — cualquier integrante debe poder explicar cualquier parte.
7. **Farmacias es reemplazable** por otro proyecto propio, siempre que cumpla las 6 condiciones de viabilidad — pero se evalúa con la misma rúbrica.
8. Fecha/logística oficial **no está en este material** — hay que confirmarla por el canal oficial del curso.