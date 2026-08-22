/**
 * dom.js — capa de presentación: crear/actualizar elementos del chat.
 * No sabe nada de fetch ni de la API — solo recibe datos y los muestra.
 */
window.App = window.App || {};

window.App.dom = (function () {
  const chatLog = document.getElementById("chatLog");
  const emptyState = document.getElementById("emptyState");

  const statusDot = document.getElementById("statusDot");
  const statusText = document.getElementById("statusText");

  const mcpStatusDot = document.getElementById("mcpStatusDot");
  const mcpStatusText = document.getElementById("mcpStatusText");

  const sendButton = document.getElementById("sendButton");
  const userIdDisplay = document.getElementById("userIdDisplay");

  function clearEmptyState() {
    if (emptyState && emptyState.isConnected) {
      emptyState.remove();
    }
  }

  function scrollToBottom() {
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function addMessage(role, text, { blocked = false } = {}) {
    clearEmptyState();

    const bubble = document.createElement("div");
    bubble.className = `msg msg--${role}` + (blocked ? " is-blocked" : "");
    bubble.textContent = text;

    chatLog.appendChild(bubble);
    scrollToBottom();

    return bubble;
  }

  function addTypingIndicator() {
    const indicator = document.createElement("div");

    indicator.className = "typing-indicator";
    indicator.id = "typingIndicator";
    indicator.setAttribute("aria-label", "El asistente está escribiendo");
    indicator.innerHTML = "<span></span><span></span><span></span>";

    chatLog.appendChild(indicator);
    scrollToBottom();
  }

  function removeTypingIndicator() {
    const indicator = document.getElementById("typingIndicator");

    if (indicator) {
      indicator.remove();
    }
  }

  function setConnectionStatus(isOk, label) {
    statusDot.className = "status-dot " + (isOk ? "is-ok" : "is-error");
    statusText.textContent = label;
  }

  function setMcpStatus(isOk, label) {
    mcpStatusDot.className = "status-dot " + (isOk ? "is-ok" : "is-error");
    mcpStatusText.textContent = label;
  }

  function setSending(isSending) {
    sendButton.disabled = isSending;
  }

  // Muestra el user_id (nombre amigable, ej. "Valentina482") en la UI.
  // "—" cuando aún no hay sesión creada.
  function setUserId(userId) {
    if (userIdDisplay) {
      userIdDisplay.textContent = userId || "—";
    }
  }

  // Vuelve el chat a su estado inicial (usado al generar una sesión
  // nueva: nuevo user_id = memoria nueva en el backend, así que el
  // historial visible también debe empezar de cero).
  function resetChat() {
    chatLog.innerHTML = "";
    chatLog.appendChild(emptyState);
  }

  // --- Panel de historial (botón "Ver historial") -------------------------
  // Estilos inline a propósito: no se toca css/styles.css para no
  // arriesgar romper reglas existentes que no están a la vista acá. Es
  // un overlay simple, suficiente para mostrar el historial en la demo.
  let _historialOverlay = null;

  function showHistorial(userId, mensajes) {
    hideHistorial(); // por si ya había uno abierto

    const overlay = document.createElement("div");
    overlay.id = "historialOverlay";
    overlay.style.cssText = [
      "position:fixed", "inset:0", "background:rgba(0,0,0,0.6)",
      "display:flex", "align-items:center", "justify-content:center",
      "z-index:1000", "padding:24px",
    ].join(";");

    const panel = document.createElement("div");
    panel.style.cssText = [
      "background:#0f1420", "color:#e6e9ef", "border:1px solid #2a3040",
      "border-radius:12px", "max-width:640px", "width:100%",
      "max-height:80vh", "overflow-y:auto", "padding:20px",
      "font-family:inherit",
    ].join(";");

    const header = document.createElement("div");
    header.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;";
    header.innerHTML = `<strong>Historial de ${userId}</strong>`;

    const closeBtn = document.createElement("button");
    closeBtn.textContent = "Cerrar";
    closeBtn.style.cssText = [
      "background:transparent", "border:1px solid #3a4050", "color:#e6e9ef",
      "border-radius:8px", "padding:6px 12px", "cursor:pointer",
    ].join(";");
    closeBtn.addEventListener("click", hideHistorial);
    header.appendChild(closeBtn);
    panel.appendChild(header);

    if (!mensajes || mensajes.length === 0) {
      const vacio = document.createElement("p");
      vacio.textContent = "Todavía no hay historial para esta sesión.";
      vacio.style.color = "#9aa3b2";
      panel.appendChild(vacio);
    } else {
      mensajes.forEach((m) => {
        const linea = document.createElement("div");
        const esHuman = m.tipo === "human";
        linea.style.cssText = [
          "margin-bottom:12px", "padding:10px 12px", "border-radius:8px",
          "white-space:pre-wrap",
          esHuman ? "background:#1c2740" : "background:#131a28",
          esHuman ? "border-left:3px solid #5b8cff" : "border-left:3px solid #17C988",
        ].join(";");
        const etiqueta = document.createElement("div");
        etiqueta.textContent = esHuman ? "Tú" : "Asistente";
        etiqueta.style.cssText = "font-size:11px;opacity:0.7;margin-bottom:4px;";
        linea.appendChild(etiqueta);
        const texto = document.createElement("div");
        texto.textContent = m.contenido;
        linea.appendChild(texto);
        panel.appendChild(linea);
      });
    }

    overlay.appendChild(panel);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) hideHistorial();
    });
    document.body.appendChild(overlay);
    _historialOverlay = overlay;
  }

  function hideHistorial() {
    if (_historialOverlay) {
      _historialOverlay.remove();
      _historialOverlay = null;
    }
  }

  return {
    addMessage,
    addTypingIndicator,
    removeTypingIndicator,
    setConnectionStatus,
    setMcpStatus,
    setSending,
    setUserId,
    resetChat,
    showHistorial,
    hideHistorial,
  };
})();