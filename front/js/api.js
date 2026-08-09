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
   * Crea una sesión anónima nueva — sin login, sin datos personales.
   * Devuelve { token: "..." }, que hay que guardar y reutilizar.
   */
  async function createSession(apiUrl) {
    const response = await fetch(normalizeUrl(apiUrl) + "/session", { method: "POST" });
    if (!response.ok) {
      throw new Error("No se pudo crear la sesión, status " + response.status);
    }
    return response.json(); // { token: "..." }
  }

  /**
   * Envía una pregunta al endpoint /chat, autenticada con el token de
   * sesión (header Authorization), no con un user_id en el body.
   * Lanza un error tipado (con .status y .detail) para que quien llama
   * decida cómo mostrarlo, sin acoplar esta función a la UI.
   */
  async function sendMessage(apiUrl, token, pregunta) {
    const response = await fetch(normalizeUrl(apiUrl) + "/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token,
      },
      body: JSON.stringify({ pregunta }),
    });

    if (!response.ok) {
      const error = new Error("La API respondió con status " + response.status);
      error.status = response.status;
      try {
        const body = await response.json();
        error.detail = body.detail;
      } catch (_parseError) {
        error.detail = null;
      }
      throw error;
    }

    return response.json(); // { respuesta: "...", token: "..." } — token RENOVADO
  }

  return { checkHealth, createSession, sendMessage };
})();