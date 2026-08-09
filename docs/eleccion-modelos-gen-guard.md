# Elección de modelos: GEN_MODEL y GUARD_MODEL

Este documento registra la evaluación comparativa que llevó a la elección final de
`GEN_MODEL` (modelo del agente) y `GUARD_MODEL` (modelo de las guardas de seguridad),
y la configuración de resiliencia (`resilience.py`) que respalda a ambos.

Dataset: `eval/preguntas_respondibles.md` (4 preguntas informativas) +
`eval/preguntas_no_respondibles.md` (6 preguntas adversarias), 10 en total,
evaluado con `eval_langsmith.py` sobre 5 métricas (`bloqueo_correcto`, `correctness`,
`faithfulness`, `no_recomienda_dosis`, `relevance`).

## Diseño del experimento

Comparación factorial completa: los tres modelos candidatos (`gpt-5.4-mini`,
`gpt-5.4-nano`, `gpt-5.6-luna`) se probaron en **ambos roles**, `GEN_MODEL` y
`GUARD_MODEL`, de forma cruzada — 9 combinaciones en total. Esto evita el error
detectado al inicio del proceso, donde `resilience.py` leía `GEN_MODEL` para las
guardas por error, acoplando ambas decisiones sin querer (ver Fix #1 en el historial
del proyecto).

`bloqueo_correcto` es la métrica central para evaluar `GUARD_MODEL`, porque mide
directamente si la guarda bloquea lo que debe bloquear y deja pasar lo que debe
dejar pasar — es el trabajo específico de ese componente, y es la condición dura de
la rúbrica del curso (criterio 5: no diagnosticar, prescribir ni recomendar dosis).

## Matriz completa: `bloqueo_correcto`

| `GUARD_MODEL` \ `GEN_MODEL` | `gpt-5.4-mini` | `gpt-5.4-nano` | `gpt-5.6-luna` |
|---|---|---|---|
| `gpt-5.4-mini` | 1.00 | 0.80 | 1.00 |
| `gpt-5.4-nano` | 1.00 | 0.89 | 0.80 |
| **`gpt-5.6-luna`** | **1.00** | **1.00** | **1.00** |

`gpt-5.6-luna` como `GUARD_MODEL` es la única fila perfecta en toda la matriz —
bloquea correctamente sin importar qué modelo genere la respuesta del agente. Las
otras dos guardas fallan al menos en una combinación, con causas raíz distintas:

- **`GUARD_MODEL=gpt-5.4-nano`**: sobre-bloquea (falsos positivos). Con
  `GEN_MODEL=nano` y con `GEN_MODEL=luna`, bloqueó preguntas puramente informativas
  (Viadil, Aspirin) alegando una "coincidencia síntoma↔indicación" que no existía en
  el texto. Es una guarda frágil ante variación de estilo del agente.
- **`GUARD_MODEL=gpt-5.4-mini`**: falla solo con `GEN_MODEL=nano` (0.80) — pero en
  este caso el bloqueo fue correcto en rigor: `nano` alucinó un disclaimer de síntoma
  que no estaba en la pregunta ("si tienes dolor o malestar..."), y la guarda de
  `mini` detectó esa alucinación y bloqueó como corresponde. El problema real está en
  `GEN_MODEL=nano`, no en la guarda.

## Matriz completa: `correctness`

| `GUARD_MODEL` \ `GEN_MODEL` | `gpt-5.4-mini` | `gpt-5.4-nano` | `gpt-5.6-luna` |
|---|---|---|---|
| `gpt-5.4-mini` | 0.75 | 0.50 | 0.75 |
| `gpt-5.4-nano` | 0.75 | 0.75 | 0.50 |
| **`gpt-5.6-luna`** | **1.00** | 0.75 | 0.75 |

Solo aplica a preguntas informativas (4 de 10). El 0.75 recurrente en varias celdas
corresponde al mismo caso ya documentado: la pregunta de Viadil, donde el RAG
recupera Venlafaxina por similitud de embeddings — un falso negativo del evaluador
que penaliza `correctness` de forma pareja en casi todas las combinaciones, no un
fallo específico de ningún modelo. La única celda perfecta (`GUARD_MODEL=luna`,
`GEN_MODEL=mini` = 1.00) sugiere que esa combinación puntual esquivó el caso, pero
no hay evidencia suficiente para generalizarlo — la causa raíz sigue siendo el
retriever, no el LLM.

## Matriz completa: `faithfulness`

| `GUARD_MODEL` \ `GEN_MODEL` | `gpt-5.4-mini` | `gpt-5.4-nano` | `gpt-5.6-luna` |
|---|---|---|---|
| `gpt-5.4-mini` | 0.86 | 0.71 | 0.90 |
| `gpt-5.4-nano` | 0.73 | 0.69 | 0.69 |
| **`gpt-5.6-luna`** | 0.78 | 0.81 | **0.91** |

`GEN_MODEL=gpt-5.6-luna` tiene el mejor `faithfulness` en dos de las tres filas, y
`GEN_MODEL=gpt-5.4-nano` el peor en todas — consistente con el hallazgo de
alucinación de contexto ya documentado (agrega afirmaciones que el contexto
recuperado no respalda). `GUARD_MODEL=gpt-5.4-nano` como fila completa es la más
baja de las tres, otra señal más de que esa guarda introduce ruido en vez de
limpiar la evaluación.

## Matriz completa: `no_recomienda_dosis`

| `GUARD_MODEL` \ `GEN_MODEL` | `gpt-5.4-mini` | `gpt-5.4-nano` | `gpt-5.6-luna` |
|---|---|---|---|
| `gpt-5.4-mini` | 1.00 | 1.00 | 1.00 |
| `gpt-5.4-nano` | 1.00 | 1.00 | 1.00 |
| **`gpt-5.6-luna`** | 1.00 | 1.00 | 1.00 |

Perfecto en las 9 combinaciones. Es la condición dura de la rúbrica (criterio 5) y
ninguna combinación de modelos la viola — el `SYSTEM_PROMPT` y el diseño de las dos
guardas (`gate_entrada`/`gate_salida`) sostienen esta restricción de forma robusta
sin importar qué modelo esté detrás.

## Matriz completa: `relevance`

| `GUARD_MODEL` \ `GEN_MODEL` | `gpt-5.4-mini` | `gpt-5.4-nano` | `gpt-5.6-luna` |
|---|---|---|---|
| `gpt-5.4-mini` | 0.89 | 0.53 | 0.94 |
| `gpt-5.4-nano` | 0.76 | 0.73 | 0.51 |
| **`gpt-5.6-luna`** | 0.83 | 0.86 | **0.95** |

No es el criterio central para elegir `GUARD_MODEL` (mide calidad de la respuesta
del agente, no la decisión de bloqueo), pero confirma la misma tendencia: `luna`
como `GEN_MODEL` da el mejor resultado, especialmente bajo una guarda que no
introduce ruido propio (`luna` como `GUARD_MODEL`).

## Ranking final — GEN_MODEL (rol de agente)

Evaluado con `GUARD_MODEL` fijo en `gpt-5.6-luna` (la guarda más limpia, sin
falsos positivos que contaminen la comparación):

| Puesto | Modelo | `bloqueo_correcto` | `relevance` | Costo (10 preguntas) | Latencia mediana |
|---|---|---|---|---|---|
| 1 | **`gpt-5.6-luna`** | 1.00 | **0.95** | **$0.0041** | 1.49s |
| 2 | `gpt-5.4-nano` | 1.00 | 0.86 | $0.0045 | 1.18s |
| 3 | `gpt-5.4-mini` (línea base) | 1.00 | 0.83 | $0.0075 | 1.24s |

**`gpt-5.6-luna` gana en calidad y en costo simultáneamente.** `gpt-5.4-nano` queda
en segundo lugar solo bajo esta guarda específica — bajo `GUARD_MODEL=gpt-5.4-mini`
(línea base histórica), `nano` cae a 0.80 de `bloqueo_correcto` y 0.50 de
`correctness`, por la alucinación de contexto ya documentada (antepone sugerencia de
evaluación profesional sin que la pregunta mencione ningún síntoma). Ese hallazgo se
mantiene válido — `nano` es la opción menos confiable de las tres para el rol de
agente, con o sin guarda "generosa".

## Ranking final — GUARD_MODEL (rol de guarda)

Evaluado con `GEN_MODEL` fijo en `gpt-5.4-mini` (línea base, para no premiar a
`luna` en ambos roles a la vez):

| Puesto | Modelo | `bloqueo_correcto` | Comportamiento observado |
|---|---|---|---|
| 1 | **`gpt-5.6-luna`** | **1.00** | Sin falsos positivos ni negativos en ninguna combinación de la matriz completa |
| 2 | `gpt-5.4-mini` (línea base) | 1.00 (con `GEN_MODEL=mini`/`luna`); 0.80 con `GEN_MODEL=nano` | Confiable, pero su score cae cuando el agente alucina contexto |
| 3 | `gpt-5.4-nano` | 0.80–0.89 | Sobre-bloquea respuestas informativas legítimas; guarda menos estable |

## Decisión final

```
GEN_MODEL   = gpt-5.6-luna
GUARD_MODEL = gpt-5.6-luna
```

Mismo modelo en ambos roles: es la combinación con mejor desempeño medido en la
matriz completa, y además la más barata de las nueve combinaciones evaluadas
(~45 % más barata que la línea base `mini`/`mini` en el conjunto de 10 preguntas).
`gpt-5.4-nano` queda descartado de ambos roles por el patrón de alucinación de
contexto (como agente) y sobre-bloqueo (como guarda), documentado con evidencia
reproducible en ambas direcciones.

## Configuración de resiliencia (`resilience.py`)

`GEN_MODEL` y `GUARD_MODEL` se mantienen como variables independientes en el código
(aunque ahora compartan valor por decisión de este análisis), para no reintroducir
el acoplamiento accidental que se corrigió en el Fix #1. Cada una tiene su propia
cadena de fallback ante caída o retiro del proveedor — ver docstring de
`resilience.py` para el contexto de por qué esto no es un riesgo hipotético (retiro
de `gpt-4o-mini`, suspensión temporal de Claude Fable 5/Mythos 5 en julio 2026).

### Cadena de fallback — GEN_MODEL (`agent/graph.py`)

```
1. gpt-5.6-luna   (principal, GEN_MODEL en .env)
2. gpt-5.4-mini   (respaldo — línea base histórica, probada y estable)
3. gpt-5.4-nano   (último recurso — desempeño más débil, pero disponible y barato)
```

Implementado con `ChatOpenAI.with_fallbacks()` de LangChain, no con
`invocar_con_fallback()` de `resilience.py` — `create_react_agent` espera un
`Runnable` ya instanciado como `model`, no una función, así que se arma la cadena
al construir el agente (`_construir_modelo()` + `.with_fallbacks()`) en vez de en
cada invocación. El kwarg condicional `reasoning_effort="none"` para modelos
`gpt-5.6.x` se aplica en `_construir_modelo()`, a cualquier eslabón de la cadena
que lo necesite, no solo al principal.

Diferencia de comportamiento a tener en cuenta: si el modelo principal falla a
mitad de una respuesta con tools ya invocadas, `with_fallbacks()` reintenta la
invocación completa desde cero con el siguiente modelo, no continúa desde donde
quedó — correcto para este caso de uso (una pregunta → una respuesta).

### Cadena de fallback — GUARD_MODEL (`resilience.py`, `CADENA_MODELOS`)

```python
CADENA_MODELOS = [
    os.getenv("GUARD_MODEL", "gpt-5.6-luna"),
    "gpt-5.4-mini",
    "gpt-5.4-nano",
]
```

`invocar_con_fallback()` aplica el mismo fix de `reasoning_effort="none"` para
cualquier modelo de la cadena que empiece con `"gpt-5.6"`, y reintenta sin fijar
`temperature` si el modelo no acepta el valor pedido, antes de pasar al siguiente
eslabón. Fail-closed: si los tres modelos fallan, se propaga `RuntimeError` y las
guardas bloquean por seguridad en vez de dejar pasar sin evaluación.

**Nota sobre `gpt-5-mini` (sin punto, snapshot `2025-08-07`):** se sacó de la cadena.
Confirmado en logs reales que ya no acepta `temperature` distinto de 1 (mismo
problema detectado en `gpt-5.6-luna`, pero sin el parámetro `reasoning_effort` que
lo resuelve), y además OpenAI ya anunció su retiro de la API para el 10 de diciembre
de 2026. No tiene sentido mantenerlo como plan de respaldo cuando ya está fallando
en producción y tiene fecha de salida confirmada.

### Diagramas

![Cadena de fallback de GUARD_MODEL](cadena-guard-model.svg)

`gate_entrada`, `gate_salida` y el filtro de similitud de embeddings pasan por
`invocar_con_fallback()` — no por un re-rank (ese componente existe aparte, en
`tools/tool_rag.py`, y está desactivado por defecto con `RERANK_ACTIVADO=false`).

![Cadena de fallback de GEN_MODEL](cadena-gen-model.svg)

Desde que se agregó `with_fallbacks()`, el agente ya no depende de un solo modelo:
si `GEN_MODEL` falla o es retirado, reintenta automáticamente con el siguiente de
la cadena, igual que las guardas.

Confirmado con evidencia real en LangSmith (2026-08-09): forzando `GEN_MODEL` a un
nombre inexistente, el trace del turno muestra dos llamadas `ChatOpenAI` seguidas
dentro del mismo nodo `call_model` — la primera contra el modelo inválido, con error
`NotFoundError` en 0.29s, y la segunda contra `gpt-5.4-mini`, exitosa en 0.91s. La
respuesta llegó normal al usuario, sin error visible ni degradación notoria más allá
de la latencia extra del primer intento fallido.

## Pendiente

- Actualizar `informe-seguridad-privacidad-calidad.md` (sección 5, calidad) y el
  README con la decisión final y un enlace a este documento.