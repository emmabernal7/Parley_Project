// SportsQuant - Quant Assistant & Conversational Chat Module (ES Modules)

import { state, $, el } from "./state.js?v=2.6";
import { sendChatMessage } from "./api.js?v=2.6";
import { refreshSlip } from "./slip.js?v=2.6";

export function addMsg(text, who) {
  const box = $("#chat-msgs");
  if (!box) return;
  const m = el("div", "msg " + who, text.replace(/\n/g, "<br>"));
  box.appendChild(m);
  box.scrollTop = box.scrollHeight;
}

export async function sendChat(text, onDetailUpdate) {
  if (!text || !text.trim()) return;
  addMsg(text, "user");
  const inputEl = $("#chat-input");
  if (inputEl) inputEl.value = "";

  const box = $("#chat-msgs");
  const thinking = el("div", "msg bot", "…");
  if (box) {
    box.appendChild(thinking);
    box.scrollTop = box.scrollHeight;
  }

  try {
    const r = await sendChatMessage(state.sessionId, text);
    thinking.textContent = r.reply;
  } catch (e) {
    thinking.textContent =
      state.lang === "es"
        ? "Error al conectar con el asistente."
        : "Error reaching assistant.";
  }

  if (box) box.scrollTop = box.scrollHeight;
  await refreshSlip(onDetailUpdate);
}

export function syncPanelPositions() {
  const slipPanel = $("#slip-panel");
  const chatPanel = $("#chat-panel");
  if (!slipPanel || !chatPanel) return;
  const bothOpen =
    slipPanel.classList.contains("open") && chatPanel.classList.contains("open");
  chatPanel.classList.toggle("shift-left", bothOpen);
}

export function wireChat(onDetailUpdate) {
  const chatFab = $("#chat-fab");
  const chatClose = $("#chat-close");
  const chatSend = $("#chat-send");
  const chatInput = $("#chat-input");

  if (chatFab) {
    chatFab.onclick = () => {
      const panel = $("#chat-panel");
      if (panel) panel.classList.toggle("open");
      syncPanelPositions();
    };
  }
  if (chatClose) {
    chatClose.onclick = () => {
      const panel = $("#chat-panel");
      if (panel) panel.classList.remove("open");
      syncPanelPositions();
    };
  }
  if (chatSend) {
    chatSend.onclick = () => {
      if (chatInput) sendChat(chatInput.value, onDetailUpdate);
    };
  }
  if (chatInput) {
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") sendChat(e.target.value, onDetailUpdate);
    });
  }
  document.querySelectorAll(".chat-suggestions button").forEach((b) => {
    b.onclick = () => sendChat(b.dataset.q, onDetailUpdate);
  });
}
