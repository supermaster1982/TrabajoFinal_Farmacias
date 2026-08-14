(function () {
  const apiUrlInput = document.getElementById("apiUrl");
  apiUrlInput.value = window.App.config.DEFAULT_API_URL;
  
  const { config } = window.App;
  const { dom } = window.App;
  const { api } = window.App;

  const form = document.getElementById("chatForm");
  const textarea = document.getElementById("pregunta");
  const apiUrlInput = document.getElementById("apiUrl");

  // El token de sesión (no un user_id) se guarda acá — se crea la primera
  // vez que hace falta (ver ensureToken) y se reemplaza en cada respuesta
  // exitosa (el servidor lo renueva en cada pregunta, ver saveToken).
  let cachedToken = localStorage.getItem(config.SESSION_TOKEN_STORAGE_KEY);

  async function ensureToken() {
    if (cachedToken) return cachedToken;
    const data = await api.createSession(apiUrlInput.value);
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
      await api.checkHealth(apiUrlInput.value);
      dom.setConnectionStatus(true, "Conectado");
    } catch (_error) {
      dom.setConnectionStatus(false, "Sin conexión — revisa la URL o que el servidor esté corriendo");
    }
  }

  async function handleAsk(pregunta) {
    dom.addMessage("user", pregunta);
    dom.addTypingIndicator();
    dom.setSending(true);

    try {
      const token = await ensureToken();
      const data = await api.sendMessage(apiUrlInput.value, token, pregunta);
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
          `No se pudo conectar con ${apiUrlInput.value}. ¿Está corriendo el servidor? ¿La URL de arriba es correcta?`
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

  apiUrlInput.addEventListener("change", refreshConnectionStatus);

  // --- Arranque ---
  refreshConnectionStatus();
})();
