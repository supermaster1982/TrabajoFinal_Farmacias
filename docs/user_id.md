# Por qué necesitamos un `user_id` confiable

## Razón 1 — NO es para el caché de MINSAL

El caché de las tools de MINSAL (`consultar_farmacias_de_turno`, `consultar_farmacias_registradas`) es **global**, no por usuario. El horario de una farmacia en una comuna es el mismo dato para cualquier persona que pregunte — no depende de quién lo pida. El `user_id` no tiene relación con este caché.

## Razón 2 — SÍ es para la memoria de la conversación (la razón principal)

El `user_id` identifica el **hilo de conversación** (`thread_id` del checkpointer de LangGraph) — es lo que permite que la pregunta 2 de alguien recuerde el contexto de su pregunta 1. Es un requisito explícito de la rúbrica del curso:

> *"Historial: Dos turnos dependientes por `user_id`"* (criterio 2 y 6 de la rúbrica)

**El problema hoy**: el `user_id` es cualquier string que el cliente decide enviar, sin verificación — alguien podría, a propósito o por accidente, usar el mismo `user_id` que otra persona y terminar mezclando conversaciones, o "leyendo" el hilo de otro sin haber participado en él.

## Razón 3 — SÍ, para no exponer datos personales en la observabilidad

Cada pregunta queda trazada en LangSmith (y opcionalmente Langfuse), asociada a su `user_id`. Si ese identificador fuera algo personal (un email, un nombre), quedaría expuesto en cada traza — ya documentado como riesgo en el informe (*"preguntas de salud registradas sin política de retención"*). El identificador debe ser **anónimo por diseño**, no solo "no pedir el nombre".

## Lo que NO necesitamos, entonces

- No necesitamos saber **quién es** la persona (no hace falta un email, nombre, ni cuenta real).
- No necesitamos una base de datos de usuarios.
- No necesitamos contraseñas.

## Lo que SÍ necesitamos

Un identificador que:
1. **No se pueda falsificar/adivinar** (para que nadie "robe" el hilo de otra persona).
2. **No contenga información personal** (para que las trazas de observabilidad queden limpias).
3. Sea automático y transparente para quien usa el asistente (sin pantallas de login).

**Solución que estamos evaluando**: sesión anónima firmada por el servidor (JWT sin datos personales adentro) — el servidor genera el ID la primera vez, lo firma, y lo verifica en cada pregunta siguiente. Resuelve las 2 razones reales (memoria confiable + privacidad en trazas) sin necesitar cuentas ni base de datos.