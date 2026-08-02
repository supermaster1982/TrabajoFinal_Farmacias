/**
 * api.js — única capa que conoce el contrato HTTP del backend.
 * Ningún otro archivo hace fetch() directo — si el contrato cambia
 * (ej. nuevos campos, otra ruta), solo se toca este archivo.
 */
window.App = window.App || {};

window.App.api = (function () {
  function normalizeUrl(url) {
    return url.replace(/\/$/, "");
  }

  async function checkHealth(apiUrl) {
    const response = await fetch(normalizeUrl(apiUrl) + "/", { method: "GET" });
    if (!response.ok) {
      throw new Error("health check devolvió status " + response.status);
    }
    return response.json();
  }

  /**
   * Envía una pregunta al endpoint /chat.
   * Lanza un error tipado (con .status y .detail) para que quien llama
   * decida cómo mostrarlo, sin acoplar esta función a la UI.
   */
  async function sendMessage(apiUrl, userId, pregunta) {
    const response = await fetch(normalizeUrl(apiUrl) + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, pregunta }),
    });

    if (!response.ok) {
      const error = new Error("La API respondió con status " + response.status);
      error.status = response.status;
      // FastAPI manda el mensaje de HTTPException como {"detail": "..."}
      try {
        const body = await response.json();
        error.detail = body.detail;
      } catch (_parseError) {
        error.detail = null;
      }
      throw error;
    }

    return response.json(); // { respuesta: "..." }
  }

  return { checkHealth, sendMessage };
})();