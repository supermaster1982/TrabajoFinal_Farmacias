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
   * sesión (header Authorization). El servidor YA NO renueva el token
   * en cada respuesta — la sesión dura 45 min fijos desde que se creó
   * (ver auth.py). Por eso la respuesta ya no trae token, solo
   * { respuesta, user_id }.
   *
   * requestId (agosto 2026): UUID generado por quien llama (ver main.js,
   * crypto.randomUUID()), uno distinto por cada pregunta — no por sesión.
   * Se manda en el body como "request_id". El backend lo usa para dos
   * cosas: (1) idempotencia — si esta misma pregunta se reintenta con el
   * MISMO requestId (ej. porque este fetch tira timeout y el código de
   * arriba decide reintentar), el backend devuelve la respuesta ya
   * calculada en vez de reprocesar; (2) trazabilidad — ese mismo ID queda
   * en los logs del servidor y en la traza de LangSmith/Langfuse, así se
   * puede encontrar esta pregunta puntual en ambos lados. Parámetro
   * opcional a propósito: si no se pasa, /chat sigue funcionando exactamente
   * igual que antes de este cambio (sin cache de idempotencia para esa
   * pregunta).
   * Lanza un error tipado (con .status y .detail) para que quien llama
   * decida cómo mostrarlo, sin acoplar esta función a la UI.
   */
  async function sendMessage(apiUrl, token, pregunta, requestId) {
    const body = { pregunta };
    if (requestId) {
      body.request_id = requestId;
    }

    const response = await fetch(normalizeUrl(apiUrl) + "/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token,
      },
      body: JSON.stringify(body),
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

  /**
   * Trae el historial de conversación de la sesión actual (requiere
   * token válido — el backend saca el user_id del token, nunca de un
   * parámetro que el front podría falsificar).
   */
  async function fetchHistorial(apiUrl, token) {
    const response = await fetch(normalizeUrl(apiUrl) + "/historial", {
      method: "GET",
      headers: { Authorization: "Bearer " + token },
    });

    if (!response.ok) {
      const error = new Error("No se pudo obtener el historial, status " + response.status);
      error.status = response.status;
      throw error;
    }

    return response.json(); // { user_id: "...", mensajes: [{ tipo, contenido }, ...] }
  }

  return {
    checkHealth,
    checkMcpHealth,
    createSession,
    sendMessage,
    fetchHistorial,
  };
})();