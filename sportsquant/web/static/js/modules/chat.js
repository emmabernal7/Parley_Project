// SportsQuant - Quant Assistant & Conversational Chat Module (ES Modules)

import { state, $, el } from "./state.js?v=2.9";
import { sendChatMessage } from "./api.js?v=2.9";
import { refreshSlip } from "./slip.js?v=2.9";

export function formatMarkdown(raw) {
  if (!raw) return "";
  // 1. Escape HTML
  let s = String(raw)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // 2. Bold (**text**)
  s = s.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

  // 3. Italics (*text*)
  s = s.replace(/\*(.*?)\*/g, "<em>$1</em>");

  // 4. Bullets
  s = s.replace(/^[•\-\*]\s+(.*)$/gm, "<div style='display:flex;gap:6px;margin:2px 0;'><span style='color:var(--teal);'>•</span><span>$1</span></div>");

  // 5. Linebreaks
  s = s.replace(/\n/g, "<br>");
  return s;
}

export function addMsg(text, who) {
  const box = $("#chat-msgs");
  if (!box) return;
  const m = el("div", "msg " + who);
  m.innerHTML = formatMarkdown(text);
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
    thinking.innerHTML = formatMarkdown(r.reply);
  } catch (e) {
    thinking.textContent =
      state.lang === "es"
        ? "Error al conectar con el asistente."
        : "Error reaching assistant.";
  }

  if (box) box.scrollTop = box.scrollHeight;
  await refreshSlip(onDetailUpdate);
}

export function updateChatSuggestions() {
  const isEs = state.lang === "es";
  const btnLogros = $("#sug-logros");
  const btnCovers = $("#sug-covers");
  const btnPayout = $("#sug-payout");
  const btnSlip = $("#sug-slip");

  if (btnLogros) {
    btnLogros.textContent = isEs ? "🏆 Mejores logros" : "🏆 Best +EV bets";
    btnLogros.dataset.q = isEs ? "mejores logros de hoy" : "best value bets today";
  }
  if (btnCovers) {
    btnCovers.textContent = isEs ? "📈 Consenso Covers" : "📈 Covers consensus";
    btnCovers.dataset.q = isEs ? "consenso covers" : "covers consensus";
  }
  if (btnPayout) {
    btnPayout.textContent = isEs ? "💰 ¿Qué más paga?" : "💰 Highest payouts";
    btnPayout.dataset.q = isEs ? "que es lo que mas paga" : "highest payouts";
  }
  if (btnSlip) {
    btnSlip.textContent = isEs ? "🎲 Analizar mi boleta" : "🎲 Price my slip";
    btnSlip.dataset.q = isEs ? "analizar mi boleta" : "price my slip";
  }
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
  updateChatSuggestions();
}
