# Proceso de revisión humana de trazas

Protocolo simple para que la observabilidad (LangSmith, y opcionalmente Langfuse) no sea solo "datos que existen pero nadie mira" — define cuándo, cómo, y qué hacer con lo que se encuentre.

## Política de retención de datos

**Las trazas técnicas se conservan sin fecha de vencimiento.** Son la base de la mejora continua del sistema: permiten detectar patrones de falla a lo largo del tiempo, recalibrar parámetros con evidencia histórica (ej. el umbral de similitud 0.54 del vademécum chileno, calibrado comparando corridas con 50, 500 y 12.411 fichas — sección 5.3 del informe), y mantener el registro de los evals formales para comparar versiones del sistema entre sí. Borrar trazas periódicamente iría en contra del propio objetivo de este proceso de revisión.

**No hace falta un plazo de anonimización porque el sistema no recolecta datos personales identificables desde el diseño.** El `user_id` es un nombre de fantasía generado con Faker (ej. "Valentina482"), sin vínculo a nombre real, email, teléfono, ni ningún otro dato que identifique a una persona (ver `docs/por-que-user-id.md`). Como las trazas nunca contuvieron un "nombre" que anonimizar, no hay nada que purgar en ese sentido — la privacidad se resuelve en el punto de origen (qué se recolecta), no con un borrado posterior.

**Acceso a las trazas:** restringido a quienes tengan credenciales del proyecto en LangSmith/Langfuse — hoy, el equipo del proyecto. Si en el futuro el sistema agregara algún dato personal real (login real, email de contacto), este documento debe actualizarse con un plazo de retención explícito para ese dato puntual — hoy no aplica porque ese dato no existe.

## Frecuencia

- **Antes de cada demo o entrega** — obligatorio.
- **Semanal**, mientras el proyecto esté en desarrollo activo (opcional pero recomendado).

## Qué revisar

1. Ve a [smith.langchain.com](https://smith.langchain.com) → Traces (o el proyecto configurado en `LANGSMITH_PROJECT`).
2. Toma una **muestra de ~10 trazas recientes**, priorizando:
   - Las de mayor latencia (`Latency` ordenado descendente) — ¿hay algo anormal, o es solo una pregunta compleja legítima?
   - Las que tengan `Error` marcado — ¿el fail-closed actuó bien, o hay un error nuevo no visto antes?
   - Una mezcla de preguntas informativas y adversarias, si hay tráfico real de usuarios (no solo del dataset de eval).

## Qué buscar en cada traza

- [ ] **Falsos positivos**: ¿el guardrail bloqueó una pregunta que en realidad era benigna? (como pasó con "Providencia" y con "ibuprofeno" durante el desarrollo — ambos casos reales, encontrados así).
- [ ] **Falsos negativos**: ¿dejó pasar algo que debería haber bloqueado?
- [ ] **Alucinación/grounding roto**: ¿la respuesta dice algo que las tools no devolvieron? (revisar el nodo `retrieve`/`tools` contra la respuesta final).
- [ ] **Latencia anormal**: ¿algo tardó mucho más de lo esperado sin una razón clara (ej. reintentos de la cadena de modelos, MINSAL lento)?
- [ ] **Casos límite nuevos**: preguntas con una forma que no está en `eval/*.md` todavía, y que revelan un comportamiento no probado antes.

## Qué hacer si se encuentra algo

Mismo patrón que se usó durante todo el desarrollo de este proyecto (documentado en el historial de commits y en "Mejoras recientes" del `README.md`):

1. **Confirmar el hallazgo** con la traza real (captura o link), no solo sospecha.
2. **Agregar el caso** a `eval/preguntas_respondibles.md` o `eval/preguntas_no_respondibles.md`, según corresponda — así queda como prueba de regresión permanente, no un hallazgo que se olvida.
3. **Corregir** (prompt de guardrail, `SYSTEM_PROMPT`, umbral de embeddings, etc., según el caso).
4. **Confirmar el fix** corriendo `eval_langsmith.py` de nuevo.
5. **Documentar** el hallazgo y el fix en el `README.md` ("Mejoras recientes") y, si corresponde, en la matriz de riesgos del informe.

## Responsable

Cualquier integrante del equipo puede hacer esta revisión — no requiere conocimiento previo del código, solo acceso a LangSmith y seguir esta checklist. Se recomienda rotar quién la hace, para que más de una persona esté familiarizada con las trazas reales del sistema (útil también de cara a la demo, donde cualquiera debe poder explicar cualquier parte).