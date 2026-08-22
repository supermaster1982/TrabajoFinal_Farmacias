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

  return {
    addMessage,
    addTypingIndicator,
    removeTypingIndicator,
    setConnectionStatus,
    setMcpStatus,
    setSending,
    setUserId,
    resetChat,
  };
})();