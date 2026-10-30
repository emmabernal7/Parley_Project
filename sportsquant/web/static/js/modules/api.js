// SportsQuant - HTTP REST API Client (ES Modules)

export async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    throw new Error(`API ${path} -> ${r.status}`);
  }
  return r.json();
}

export function postJSON(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const getEvents = (sport) =>
  api("/api/events" + (sport ? "?sport=" + encodeURIComponent(sport) : ""));

export const getEvent = (id) =>
  api("/api/event/" + encodeURIComponent(id));

export const setUserOdds = (id, key, odds) =>
  postJSON(`/api/event/${encodeURIComponent(id)}/odds`, { key, odds });

export const refreshEvents = () =>
  postJSON("/api/events/refresh", {});

export const getSettings = () =>
  api("/api/settings");

export const getBets = () =>
  api("/api/bets");

export const getBankrollSummary = () =>
  api("/api/bankroll");

export const deleteBet = (id) =>
  api("/api/bets/" + encodeURIComponent(id), { method: "DELETE" });

export const clearAllBets = () =>
  api("/api/bets", { method: "DELETE" });

export const getSlip = (sessionId) =>
  api("/api/slip?session_id=" + encodeURIComponent(sessionId));

export const addSlipLeg = (sessionId, eventId, key) =>
  postJSON("/api/slip/add", { session_id: sessionId, event_id: eventId, key });

export const removeSlipLeg = (sessionId, eventId, key) =>
  postJSON("/api/slip/remove", { session_id: sessionId, event_id: eventId, key });

export const clearSlip = (sessionId) =>
  postJSON("/api/slip/clear", { session_id: sessionId });

export const placePaperBet = (sessionId, stake) =>
  postJSON("/api/bets", { session_id: sessionId, stake });

export const sendChatMessage = (sessionId, message) =>
  postJSON("/api/chat", { session_id: sessionId, message });
