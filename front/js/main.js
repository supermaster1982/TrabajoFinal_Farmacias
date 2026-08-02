/**
 * main.js — punto de entrada. Conecta config.js + dom.js + api.js y
 * maneja los eventos de la UI. No define lógica de red ni de renderizado
 * propia — delega en los otros módulos.
 */
(function () {
  const { config } = window.App;
  const { dom } = window.App;
  const { api } = window.App;

  const form = document.getElementById("chatForm");
  const textarea = document.getElementById("pregunta");
  const apiUrlInput = document.getElementById("apiUrl");

  const userId = getOrCreateUserId();

  function getOrCreateUserId() {
    let id = localStorage.getItem(config.USER_ID_STORAGE_KEY);
    if (!id) {
      id = "web-" + crypto.randomUUID();
      localStorage.setItem(config.USER_ID_STORAGE_KEY, id);
    }
    return id;
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
      const data = await api.sendMessage(apiUrlInput.value, userId, pregunta);
      dom.removeTypingIndicator();
      const wasBlocked = (data.respuesta || "").includes(config.GUARDRAIL_MARKER);
      dom.addMessage("assistant", data.respuesta, { blocked: wasBlocked });
    } catch (error) {
      dom.removeTypingIndicator();
      if (error.status) {
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
