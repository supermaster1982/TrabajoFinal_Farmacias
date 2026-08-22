(function () {

  const { config } = window.App;
  const { dom } = window.App;
  const { api } = window.App;

  const form = document.getElementById("chatForm");
  const textarea = document.getElementById("pregunta");
  const backendUrlInput = document.getElementById("backendUrl");
  const mcpUrlInput = document.getElementById("mcpUrl");
  const newSessionBtn = document.getElementById("newSessionBtn");

  // Token y user_id de sesión — se crean juntos (ver ensureSession) y
  // viven juntos: nunca debería haber un token guardado sin su user_id
  // correspondiente, o la UI mostraría un nombre que no es el real.
  let cachedToken = localStorage.getItem(config.SESSION_TOKEN_STORAGE_KEY);
  let cachedUserId = localStorage.getItem(config.USER_ID_STORAGE_KEY);
  let mcpAvailable = false;

  // Si al cargar hay un token pero no hay user_id (o viceversa, restos de
  // una versión vieja del front), se descarta todo y se pide sesión nueva.
  if (!cachedToken || !cachedUserId) {
    cachedToken = null;
    cachedUserId = null;
    localStorage.removeItem(config.SESSION_TOKEN_STORAGE_KEY);
    localStorage.removeItem(config.USER_ID_STORAGE_KEY);
  }
  dom.setUserId(cachedUserId);

  async function ensureSession() {
    if (cachedToken && cachedUserId) return cachedToken;
    const data = await api.createSession(backendUrlInput.value);
    saveSession(data.user_id, data.token);
    return cachedToken;
  }

  function saveSession(userId, token) {
    cachedToken = token;
    cachedUserId = userId;
    localStorage.setItem(config.SESSION_TOKEN_STORAGE_KEY, token);
    localStorage.setItem(config.USER_ID_STORAGE_KEY, userId);
    dom.setUserId(userId);
  }

  function clearSession() {
    cachedToken = null;
    cachedUserId = null;
    localStorage.removeItem(config.SESSION_TOKEN_STORAGE_KEY);
    localStorage.removeItem(config.USER_ID_STORAGE_KEY);
    dom.setUserId(null);
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
      const token = await ensureSession();
      const data = await api.sendMessage(backendUrlInput.value, token, pregunta);
      // Ya no hay token que renovar (dura 45 min fijos). Si el user_id
      // que confirma el backend difiere del que teníamos cacheado,
      // reflejamos el real — no debería pasar salvo bug de servidor.
      if (data.user_id && data.user_id !== cachedUserId) {
        cachedUserId = data.user_id;
        localStorage.setItem(config.USER_ID_STORAGE_KEY, data.user_id);
        dom.setUserId(data.user_id);
      }
      dom.removeTypingIndicator();

      const wasBlocked = (data.respuesta || "")
        .includes(config.GUARDRAIL_MARKER);

      dom.addMessage(
        "assistant",
        data.respuesta,
        { blocked: wasBlocked }
      );

    } catch (error) {

      dom.removeTypingIndicator();

      if (error.status === 401) {
        // Sesión expirada (45 min fijos, sin renovación) — se limpian
        // token + user_id; la próxima pregunta crea una sesión (y un
        // user_id) nuevos automáticamente.
        clearSession();
        dom.addMessage(
          "error",
          "⚠️ No fue posible renovar la sesión. Intenta nuevamente."
        );

      } else if (error.status === 503) {

        dom.addMessage(
          "error",
          "⚠️ El control de seguridad no está disponible en este momento (falla del proveedor del modelo). " +
          "Por seguridad, no se procesó tu pregunta. Intenta de nuevo en un momento."
        );

      } else if (error.status) {

        dom.addMessage(
          "error",
          `El servidor respondió con un error (${error.status}). Revisa los logs de la terminal.`
        );

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

    textarea.style.height =
      Math.min(
        textarea.scrollHeight,
        120
      ) + "px";
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

    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {

      event.preventDefault();

      form.requestSubmit();

    }
  });

  textarea.addEventListener(
    "input",
    autoGrowTextarea
  );

  // Solo los chips de preguntas sugeridas (tienen data-q). El botón de
  // "generar otro nombre" también usa la clase .chip por estilo, pero
  // su comportamiento se registra aparte, más abajo.
  document.querySelectorAll(".chip[data-q]").forEach((chip) => {
    chip.addEventListener("click", () => handleAsk(chip.dataset.q));
  });

  // Botón "generar otro nombre": nueva identidad = nueva memoria en el
  // backend. No se puede "renombrar" una sesión sin perder su historial,
  // así que acá se limpia también el chat visible para que quede
  // consistente con lo que realmente pasó del lado del servidor.
  if (newSessionBtn) {
    newSessionBtn.addEventListener("click", async () => {
      clearSession();
      dom.resetChat();
      try {
        await ensureSession();
      } catch (_error) {
        dom.addMessage("error", "No se pudo generar una sesión nueva. Revisa la conexión con el backend.");
      }
    });
  }

  backendUrlInput.addEventListener("change", refreshConnectionStatus);
  mcpUrlInput.addEventListener("change", refreshConnectionStatus);

  // --- Arranque ---

  refreshConnectionStatus();

  // Si no hay sesión guardada (primera visita, o se limpió por expirar),
  // se crea una apenas carga la página — así el nombre aparece de
  // entrada, sin esperar a la primera pregunta. Si falla (ej. backend
  // caído al abrir), no se muestra error acá: se reintenta solo al
  // primer intento de pregunta, dentro de handleAsk.
  if (!cachedToken || !cachedUserId) {
    ensureSession().catch(() => {
      // silencioso: el estado del backend ya se refleja en el punto de
      // arriba (refreshConnectionStatus); no hace falta duplicar el aviso.
    });
  }
})();
