window.App = window.App || {};

window.App.api = (function () {
  function normalizeUrl(url) {
    return url.replace(/\/$/, "");
  }

  async function checkHealth(backendUrl) {
    const response = await fetch(normalizeUrl(backendUrl) + "/", { method: "GET" });
    if (!response.ok) {
      throw new Error("health check devolvió status " + response.status);
    }
    return response.json();
  }

  async function checkMcpHealth(mcpUrl) {
    const response = await fetch(
      normalizeUrl(mcpUrl) + "/health",
      { method: "GET" }
    );

    if (!response.ok) {
      throw new Error(
        "health check del MCP devolvió status " + response.status
      );
    }

    return response.json();
  }

  /**
   * Crea una sesión anónima nueva — sin login, sin datos personales.
   * Devuelve { user_id: "Valentina482", token: "..." }.
   * El user_id es el nombre amigable que hay que MOSTRAR en la UI — es
   * literalmente el valor que viaja en el contrato {user_id, pregunta}.
   */
  async function createSession(apiUrl) {
    const response = await fetch(normalizeUrl(apiUrl) + "/session", { method: "POST" });
    if (!response.ok) {
      throw new Error("No se pudo crear la sesión, status " + response.status);
    }
    return response.json(); // { user_id: "...", token: "..." }
  }

  /**
   * Envía una pregunta al endpoint /chat, autenticada con el token de
   * sesión (header Authorization), no con un user_id en el body.
   * El servidor YA NO renueva el token en cada respuesta — la sesión
   * dura 45 min fijos desde que se creó (ver auth.py). Por eso la
   * respuesta ya no trae token, solo { respuesta, user_id }.
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

    return response.json(); // { respuesta: "...", user_id: "..." } — sin token
  }

  return {
    checkHealth,
    checkMcpHealth,
    createSession,
    sendMessage,
  };
})();