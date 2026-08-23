(function () {

  const { config } = window.App;
  const { dom } = window.App;
  const { api } = window.App;

  const form = document.getElementById("chatForm");
  const textarea = document.getElementById("pregunta");
  const backendUrlInput = document.getElementById("backendUrl");
  const mcpUrlInput = document.getElementById("mcpUrl");
  const newSessionBtn = document.getElementById("newSessionBtn");
  const verHistorialBtn = document.getElementById("verHistorialBtn");

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

  // Genera un ID único por PREGUNTA (no por sesión) — ver docstring de
  // sendMessage() en api.js para qué hace el backend con esto
  // (idempotencia + trazabilidad). crypto.randomUUID() es nativo del
  // navegador, sin dependencias nuevas; disponible en todos los
  // navegadores modernos servidos por HTTPS (o localhost).
  function generarRequestId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    // Respaldo simple por si algún navegador viejo no tiene randomUUID —
    // no necesita ser criptográficamente perfecto, solo único para
    // efectos de idempotencia/trazabilidad de esta pregunta puntual.
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

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

    // Crear la sesión solamente después de confirmar
    // que el backend está disponible.
    if (!cachedToken || !cachedUserId) {
      try {
        await ensureSession();
      } catch (error) {
        console.error("Error creando sesión:", error);
        dom.setUserId(null);
      }
    }

  } catch (error) {
    console.error("Backend no disponible:", error);
    dom.setConnectionStatus(false, "Backend sin conexión");
  }

  try {
    await api.checkMcpHealth(mcpUrlInput.value);
    mcpAvailable = true;
    dom.setMcpStatus(true, "MCP disponible");
  } catch (error) {
    console.error("MCP no disponible:", error);
    mcpAvailable = false;
    dom.setMcpStatus(false, "MCP no disponible");
  }
}

  async function handleAsk(pregunta) {
    // Antes: si mcpAvailable era false, se bloqueaba CUALQUIER pregunta acá
    // mismo, sin ni siquiera intentar mandarla al backend — incluso
    // preguntas que no necesitan el MCP para nada (ej. vademécum
    // internacional, MINSAL). Esto anulaba la resiliencia real que el
    // backend ya tiene: si una tool puntual falla, el agente sigue
    // funcionando para todo lo demás (ver tool_rag_chile.py). El
    // indicador "MCP disponible/no disponible" en la barra de estado
    // sigue siendo útil como información visual, pero ya no bloquea nada
    // acá — es el backend quien decide, tool por tool, qué puede resolver.
    dom.addMessage("user", pregunta);
    dom.addTypingIndicator();
    dom.setSending(true);

    // Un request_id nuevo por cada pregunta — se genera UNA vez acá,
    // antes del intento. Si más adelante se agrega lógica de reintento
    // automático ante timeout, debe reusarse este MISMO requestId en el
    // reintento (no generar uno nuevo) para que la idempotencia del
    // backend funcione — es la razón de ser de este ID.
    const requestId = generarRequestId();

    try {
      const token = await ensureSession();
      const data = await api.sendMessage(backendUrlInput.value, token, pregunta, requestId);
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
    const textoOriginal = newSessionBtn.textContent;

    newSessionBtn.disabled = true;
    newSessionBtn.textContent = "Generando...";

    clearSession();
    dom.resetChat();

    try {
      await ensureSession();

      console.log("Nueva sesión creada:", cachedUserId);

    } catch (error) {
      console.error("Error creando nueva sesión:", error);

      dom.addMessage(
        "error",
        "No se pudo crear una nueva sesión. Intenta nuevamente."
      );

    } finally {
      newSessionBtn.disabled = false;
      newSessionBtn.textContent = textoOriginal;
    }
  });
}

  // Botón "Ver historial": trae la conversación guardada en Postgres para
  // la sesión actual y la muestra en un panel superpuesto. Requiere una
  // sesión activa (token válido) — si no hay, se crea una primero.
  if (verHistorialBtn) {
    verHistorialBtn.addEventListener("click", async () => {
      try {
        const token = await ensureSession();
        const data = await api.fetchHistorial(backendUrlInput.value, token);
        dom.showHistorial(data.user_id, data.mensajes);
      } catch (error) {
        if (error.status === 401) {
          clearSession();
          dom.addMessage("error", "⚠️ Tu sesión expiró. Envía una pregunta para crear una sesión nueva.");
        } else {
          dom.addMessage("error", "No se pudo obtener el historial. Revisa la conexión con el backend.");
        }
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
  
})();
