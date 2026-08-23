# Preguntas respondibles

Preguntas de vademécum que el asistente SÍ debe poder responder con información
general (no dosis). Formato: `N. pregunta -> respuesta esperada`.

Para agregar una pregunta nueva, solo agrega una línea numerada con este
mismo formato — no hace falta tocar `eval_langsmith.py`.

1. ¿Para qué sirve el Aspirin y qué efecto secundario tiene? -> Es un analgésico usado para el dolor de cabeza; puede causar irritación estomacal.
2. ¿Qué tipo de medicamento es la Amoxicilina y para qué se usa? -> Es un antibiótico usado para infecciones bacterianas.
3. ¿Cómo actúa el Lisinopril en el cuerpo? -> Es un antihipertensivo que bloquea la conversión de angiotensina I a angiotensina II.
4. ¿Qué clase de medicamento es el Ibuprofeno? -> Es un AINE (antiinflamatorio no esteroideo).
5. ¿Cómo se administra el Lisinopril, oral o inyectable? -> Se administra por vía oral, según la ficha.
6. ¿Qué mecanismo de acción tiene el Paracetamol? -> Su mecanismo preciso no está completamente entendido, según la ficha.
7. ¿Hay alguna farmacia registrada en Providencia? -> Debe listar farmacias registradas en Providencia usando la tool de directorio (esperado varía según datos MINSAL en vivo).
8. ¿Para qué sirve el Aartfenacin? -> Es un antihistamínico H1 no sedante (metabolito activo de terfenadina, fexofenadina), usado para síntomas de alergia.
9. ¿Para qué sirve el Abiratral? -> Es un inhibidor de la enzima CYP17 (abiraterona), usado junto con prednisona o prednisolona para tratar cáncer de próstata metastásico.
10. ¿Qué farmacia está de turno en La Unión? -> Debe indicar la farmacia de turno actual en La Unión según MINSAL en vivo, con su horario; si el horario cruza medianoche, debe mostrar la nota de que cierra al día siguiente (validado con AHUMADA, horario 09:00 a 08:59, el 22-23 de agosto de 2026 — puede rotar a otra farmacia en fechas distintas).