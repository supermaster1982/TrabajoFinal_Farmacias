# Por qué necesitamos un `user_id` confiable

## Razón 1 — NO es para el caché de MINSAL

El caché de las tools de MINSAL (`consultar_farmacias_de_turno`, `consultar_farmacias_registradas`) es **global**, no por usuario. El horario de una farmacia en una comuna es el mismo dato para cualquier persona que pregunte — no depende de quién lo pida. El `user_id` no tiene relación con este caché.

## Razón 2 — SÍ es para la memoria de la conversación (la razón principal)

El `user_id` identifica el **hilo de conversación** (`thread_id` del checkpointer de LangGraph) — es lo que permite que la pregunta 2 de alguien recuerde el contexto de su pregunta 1. Es un requisito explícito de la rúbrica del curso:

> *"Historial: Dos turnos dependientes por `user_id`"* (criterio 2 y 6 de la rúbrica)

**El problema real que esto resuelve**: sin un `user_id` verificado, alguien podría, a propósito o por accidente, usar el mismo `user_id` que otra persona y terminar mezclando conversaciones, o "leyendo" el hilo de otro sin haber participado en él.

**Dos caminos, uno seguro y uno directo (decisión de diseño, no un problema pendiente):**
- **Con token** (de `POST /session`): el `user_id` real es el firmado dentro del JWT — el servidor lo verifica en cada pregunta, así nadie puede usar el `user_id` de otra persona.
- **Sin token** (solo `user_id` en el body): se acepta tal cual, sin verificación de firma. Este camino existe a propósito para satisfacer el contrato literal que pide la rúbrica (`POST {user_id, pregunta}`) y para poder probar la API directo, sin pasar por `/session` primero. Quien usa este camino no tiene la protección de que otro "adivine" su `user_id` — mismo trade-off que cualquier API que acepta un ID plano en el body. El front de producción siempre usa el camino con token.

**Persistencia (agosto 2026):** el historial de conversación asociado a cada `user_id` ya no vive en memoria del proceso — se guarda en una base Postgres real (`PostgresSaver`), y sobrevive a un reinicio del servidor. Detalle completo, con la validación real, en el informe de seguridad (sección 3.13).

## Razón 3 — SÍ, para no exponer datos personales en la observabilidad

Cada pregunta queda trazada en LangSmith (y opcionalmente Langfuse), asociada a su `user_id`. Si ese identificador fuera algo personal (un email, un nombre real), quedaría expuesto en cada traza. El identificador debe ser **anónimo por diseño**, no solo "no pedir el nombre".

**Cómo se resuelve esto en la práctica:** el `user_id` es un **nombre de fantasía generado con Faker** (ej. "Valentina482", "Rodrigo9719") — se ve y se siente como un nombre real para que la persona pueda identificar su sesión en la interfaz, pero no está vinculado a ninguna identidad real. Se muestra directamente en el front (barra de sesión, con un botón para generar uno nuevo cuando se quiera) precisamente porque no revela nada personal al mostrarlo.

Esto también es la base de la política de retención de datos del proyecto (`docs/proceso-revision-trazas.md`): como el identificador nunca contuvo un dato personal real, las trazas técnicas se pueden conservar sin fecha de vencimiento (útiles para mejora continua) sin que eso sea un problema de privacidad.

## Lo que NO necesitamos, entonces

- No necesitamos saber **quién es** la persona (no hace falta un email, nombre real, ni cuenta real).
- No necesitamos una base de datos de usuarios ni contraseñas.
- No necesitamos que la persona recuerde ni escriba ningún identificador — se genera solo.

## Lo que SÍ necesitamos

Un identificador que:
1. **No se pueda falsificar/adivinar** en el camino de producción (para que nadie "robe" el hilo de otra persona).
2. **No contenga información personal** (para que las trazas de observabilidad queden limpias y se puedan retener indefinidamente sin riesgo).
3. Sea automático y transparente para quien usa el asistente (sin pantallas de login), pero igual visible para que la persona sepa "cuál soy yo".
4. Permita recuperar el propio historial de conversación en cualquier momento durante la sesión.

**Solución implementada**: sesión anónima firmada por el servidor — un JWT sin datos personales adentro, con un nombre amigable generado por Faker como `user_id`. El servidor genera el ID y el token la primera vez (`POST /session`), y los verifica en cada pregunta siguiente (`POST /chat`) y en la consulta de historial (`GET /historial`).

**Duración de la sesión (corregido, agosto 2026): 45 minutos fijos desde que se crea el token, sin renovarse con el uso.** Una versión anterior de este documento (y del README) describía el token como renovado en cada pregunta — eso ya no es así; fue un cambio deliberado para que un token robado, aunque siguiera en uso activo, no quedara válido indefinidamente. Al vencer, `/chat` y `/historial` responden 401, y el front pide una sesión nueva automáticamente — lo que implica memoria de conversación nueva (un `user_id` no se puede "renombrar" sin perder su historial).

Ver `docs/flujo-autenticacion.svg` para el diagrama del flujo completo, y el informe de seguridad (secciones 6.1, 3.13 y 3.14) para el detalle de persistencia, idempotencia y trazabilidad asociados a este mismo `user_id`.