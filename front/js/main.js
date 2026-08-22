(function () {
  const { config } = window.App;
  const { dom } = window.App;
  const { api } = window.App;

  const form = document.getElementById("chatForm");
  const textarea = document.getElementById("pregunta");
  const backendUrlInput = document.getElementById("backendUrl");
  const mcpUrlInput = document.getElementById("mcpUrl");

  // El token de sesión (no un user_id) se guarda acá — se crea la primera
  // vez que hace falta (ver ensureToken) y se reemplaza en cada respuesta
  // exitosa (el servidor lo renueva en cada pregunta, ver saveToken).
  let cachedToken = localStorage.getItem(config.SESSION_TOKEN_STORAGE_KEY);
  let mcpAvailable = false;

  async function ensureToken() {
    if (cachedToken) return cachedToken;
    const data = await api.createSession(backendUrlInput.value);
    cachedToken = data.token;
    localStorage.setItem(config.SESSION_TOKEN_STORAGE_KEY, cachedToken);
    return cachedToken;
  }

  function saveToken(token) {
    cachedToken = token;
    localStorage.setItem(config.SESSION_TOKEN_STORAGE_KEY, token);
  }

  function clearToken() {
    cachedToken = null;
    localStorage.removeItem(config.SESSION_TOKEN_STORAGE_KEY);
  }

  async function refreshConnectionStatus() {
    try {
      await api.checkHealth(backendUrlInput.value);
      dom.setConnectionStatus(true, "Backend conectado");
    } catch (_error) {
      dom.setConnectionStatus(false, "Backend sin conexión");
    }

    try {
      await api.checkMcpHealth(mcpUrlInput.value);
      mcpAvailable = true;
      dom.setMcpStatus(true, "MCP disponible");
    } catch (_error) {
      mcpAvailable = false;
      dom.setMcpStatus(false, "MCP no disponible");
    }
  }

  async function handleAsk(pregunta) {
    if (!mcpAvailable) {
      dom.addMessage(
        "error",
        `El MCP no está disponible en ${mcpUrlInput.value}. No se puede procesar la consulta.`
      );
      return;
    }
    dom.addMessage("user", pregunta);
    dom.addTypingIndicator();
    dom.setSending(true);

    try {
      const token = await ensureToken();
      const data = await api.sendMessage(backendUrlInput.value, token, pregunta);
      saveToken(data.token); // token renovado — reemplaza al anterior
      dom.removeTypingIndicator();
      const wasBlocked = (data.respuesta || "").includes(config.GUARDRAIL_MARKER);
      dom.addMessage("assistant", data.respuesta, { blocked: wasBlocked });
    } catch (error) {
      dom.removeTypingIndicator();
      if (error.status === 401) {
        // El token no era válido o expiró (45 min de inactividad) — se
        // limpia; la próxima pregunta crea una sesión nueva sola.
        clearToken();
        dom.addMessage(
          "error",
          "⚠️ Tu sesión expiró. Envía la pregunta de nuevo — se creará una sesión nueva automáticamente."
        );
      } else if (error.status === 503) {
        dom.addMessage(
          "error",
          "⚠️ El control de seguridad no está disponible en este momento (falla del proveedor del modelo). " +
          "Por seguridad, no se procesó tu pregunta. Intenta de nuevo en un momento."
        );
      } else if (error.status) {
        dom.addMessage("error", `El servidor respondió con un error (${error.status}). Revisa los logs de la terminal.`);
      } else {
        dom.addMessage(
          "error",
          `No se pudo conectar con ${backendUrlInput.value}. ¿Está corriendo el servidor? ¿La URL de arriba es correcta?`
        );
      }
    } finally {
      dom.setSending(false);
    }
  }

  function autoGrowTextarea() {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + "px";
  }

  // --- Eventos ---

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const pregunta = textarea.value.trim();
    if (!pregunta) return;
    textarea.value = "";
    autoGrowTextarea();
    handleAsk(pregunta);
  });

  textarea.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  textarea.addEventListener("input", autoGrowTextarea);

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => handleAsk(chip.dataset.q));
  });

  backendUrlInput.addEventListener("change", refreshConnectionStatus);
  mcpUrlInput.addEventListener("change", refreshConnectionStatus);

  // --- Arranque ---
  refreshConnectionStatus();
})();