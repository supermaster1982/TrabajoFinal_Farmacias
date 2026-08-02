/**
 * config.js — constantes compartidas por el resto de los módulos.
 *
 * Nota de arquitectura: se usa un namespace global (`window.App`) en vez de
 * `import`/`export` de módulos ES6, porque los módulos ES6 no cargan al
 * abrir el archivo directo con doble clic (protocolo file://) en Chrome —
 * el navegador bloquea la carga de módulos por CORS en ese protocolo.
 * Con <script> "clásicos" (sin type="module"), esta restricción no aplica.
 */
window.App = window.App || {};

window.App.config = {
  DEFAULT_API_URL: "http://localhost:8000",
  USER_ID_STORAGE_KEY: "asistente_farmacias_user_id",
  // Frase que devuelve el guardrail cuando bloquea — si aparece en la
  // respuesta, la UI resalta la burbuja para que se note en la demo que
  // el control de seguridad actuó.
  GUARDRAIL_MARKER: "requiere evaluación profesional",
};
