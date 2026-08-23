# Términos y condiciones de uso

**Asistente Informativo de Farmacias y Medicamentos**
Trabajo Final — Diplomado en IA Generativa (UEjecutivos, Universidad de Chile).

## 1. Qué es este servicio

Este es un **proyecto educativo**, desarrollado como Trabajo Final de un diplomado universitario. No es un producto comercial ni un servicio de salud. Informa sobre:
- Farmacias de turno y su directorio general, con datos consultados en vivo desde la API pública de MINSAL.
- Información general de medicamentos, citada desde dos vademécums indexados: un dataset internacional educativo ("Comprehensive Drug Information") y un vademécum chileno provisto como material de clase.

## 2. Qué NO hace este asistente

- **No diagnostica** ninguna enfermedad ni condición de salud.
- **No prescribe ni recomienda** medicamentos, dosis, horarios de administración, ni tratamientos.
- **No evalúa** si es seguro combinar un medicamento con una alergia, otro medicamento, o una condición de salud particular.
- **No confirma** stock, precio, ni disponibilidad comercial de ningún medicamento.
- **No reemplaza** una consulta, evaluación, o receta de un profesional de salud.

Si mencionas un síntoma o malestar, el asistente está diseñado para sugerirte que consultes a un profesional de salud antes de cualquier otra información — esa sugerencia no es opcional ni decorativa, es el comportamiento esperado del sistema.

## 3. Ante una urgencia o emergencia

Este asistente **no está diseñado ni debe usarse** para situaciones de urgencia o emergencia médica. Si tú o alguien cerca de ti necesita atención médica inmediata, contacta a un servicio de urgencia real (SAMU, servicio de urgencia más cercano, u otro medio equivalente) — no a este asistente.

## 4. Exactitud de la información

- Los datos de farmacias de turno provienen de una fuente externa (MINSAL) que este proyecto no controla ni puede garantizar que esté siempre actualizada o completa — pueden existir comunas sin datos, o datos desactualizados en el origen.
- Los vademécums son datasets de uso educativo — el internacional está en inglés (traducido por el sistema al responder) — que **no constituyen una fuente clínica autoritativa**: puede haber marcas comerciales no incluidas, y su información general no reemplaza el prospecto oficial de un medicamento ni el criterio de un profesional.
- Al ser un sistema basado en modelos de lenguaje, aunque se han implementado múltiples controles para evitar errores (ver capas de seguridad documentadas en `docs/capas-seguridad.svg`), **no se garantiza una exactitud del 100%** en ninguna respuesta.

## 5. Datos y privacidad

- Este proyecto usa una **sesión anónima**, no una cuenta con identidad real: al empezar a usar el asistente, el sistema genera automáticamente un nombre de fantasía (ej. "Valentina482") que identifica tu conversación — no está vinculado a tu nombre real, email, ni ningún dato personal, y vos podés generar uno nuevo cuando quieras. Esta sesión es verificada por el servidor mediante un token firmado, válido por 45 minutos desde que se crea; al vencer, se requiere una sesión nueva.
- Tu conversación (preguntas y respuestas) se guarda de forma persistente mientras dure tu sesión activa, para que el asistente recuerde el contexto entre tus mensajes. También puede quedar registrada con fines de desarrollo, depuración y evaluación de calidad de este proyecto educativo (LangSmith, y opcionalmente Langfuse) — ver la política de retención de datos en `docs/proceso-revision-trazas.md`.
- **No ingreses** información personal sensible real (nombre completo, RUT, datos de salud reales u otra información identificable) al usar este asistente — es un entorno de prueba académico, no un sistema clínico con las protecciones que eso requeriría. El nombre de sesión generado automáticamente es de fantasía; no reemplaces ese diseño escribiendo tu propio nombre real en el chat.

## 6. Uso aceptado

Al usar este asistente, aceptas que:
- Es una herramienta informativa de apoyo, no un sustituto de criterio profesional.
- Cualquier decisión sobre tu salud debe consultarse con un profesional de salud calificado.
- El equipo de desarrollo (estudiantes del diplomado) no asume responsabilidad por decisiones tomadas exclusivamente en base a las respuestas de este asistente.

## 7. Contacto

Este proyecto fue desarrollado como Trabajo Final del Diplomado en IA Generativa (UEjecutivos, Universidad de Chile). No es un canal de soporte ni un servicio con garantías de disponibilidad o continuidad.