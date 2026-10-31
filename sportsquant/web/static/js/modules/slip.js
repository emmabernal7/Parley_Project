// SportsQuant - Bet Slip & Paper Bankroll Management (ES Modules)

import { state, I18N, $, el, toast } from "./state.js?v=2.9";
import { fmtOdds, fmtSel, translateGroupName, translateLabel } from "./render.js?v=2.9";
import {
  getSlip,
  addSlipLeg,
  removeSlipLeg,
  clearSlip,
  placePaperBet,
  getSettings,
  getBets,
  getBankrollSummary,
  deleteBet,
  clearAllBets,
} from "./api.js?v=2.9";

export function isPicked(gid, sid) {
  return state.slipLegs.some(
    (l) => l.event_id === state.selectedId && l.key === gid + ":" + sid
  );
}

export function updateSlipCalculations() {
  const stakeInput = $("#slip-stake");
  const profitEl = $("#slip-profit");
  const payoutEl = $("#slip-payout");
  if (!stakeInput || !profitEl || !payoutEl) return;
  const stake = parseFloat(stakeInput.value);
  const fairOdds = state.slipFairOdds;
  if (!fairOdds || isNaN(stake) || stake <= 0) {
    profitEl.textContent = "-";
    payoutEl.textContent = "-";
    return;
  }
  const payout = stake * fairOdds;
  const profit = payout - stake;
  payoutEl.textContent = "$" + payout.toFixed(2);
  profitEl.textContent = (profit >= 0 ? "+$" : "-$") + Math.abs(profit).toFixed(2);
}

export async function toggleSlip(g, s, btn, onDetailUpdate) {
  const key = g.id + ":" + s.id;
  const picked = isPicked(g.id, s.id);
  try {
    if (picked) {
      await removeSlipLeg(state.sessionId, state.selectedId, key);
    } else {
      await addSlipLeg(state.sessionId, state.selectedId, key);
    }
    btn.classList.toggle("picked");
    await refreshSlip(onDetailUpdate);
  } catch (e) {
    toast(state.lang === "es" ? "No se pudo actualizar el boleto" : "Could not update slip");
  }
}

export async function refreshSlip(onDetailUpdate) {
  try {
    const r = await getSlip(state.sessionId);
    state.slipLegs = r.legs || [];
    const countEl = $("#slip-count");
    if (countEl) countEl.textContent = state.slipLegs.length;
    const slipFabText = $("#slip-fab-text");
    if (slipFabText) {
      const isEs = state.lang === "es";
      slipFabText.textContent = state.slipLegs.length 
        ? (isEs ? `🎟 Boleta de Apuestas (${state.slipLegs.length})` : `🎟 Bet Slip (${state.slipLegs.length})`)
        : (isEs ? "Boleta de Apuesta Simulada" : "Paper Bet Slip");
    }
    const slipFab = $("#slip-fab");
    if (slipFab) slipFab.style.display = state.slipLegs.length ? "flex" : "none";
    const chatFab = $("#chat-fab");
    if (chatFab) chatFab.classList.toggle("has-slip", state.slipLegs.length > 0);

    const legBox = $("#slip-legs");
    if (legBox) {
      legBox.innerHTML = "";
      (r.priced && r.priced.legs ? r.priced.legs : []).forEach((l, i) => {
        const leg = r.legs[i];
        const row = el("div", "slip-leg");
        row.innerHTML = `
          <div class="top">
            <span class="sel">${translateLabel(l.selection)}</span>
            <button class="rm" title="Eliminar selección">✕</button>
          </div>
          <div class="ev">${l.event} - ${translateGroupName(l.market)} - ${fmtSel({prob: l.prob, odds: l.odds != null ? l.odds : (1 / l.prob)})}</div>
        `;
        row.querySelector(".rm").onclick = async () => {
          await removeSlipLeg(state.sessionId, leg.event_id, leg.key);
          await refreshSlip(onDetailUpdate);
          if (onDetailUpdate) onDetailUpdate();
        };
        legBox.appendChild(row);
      });
    }

    const probEl = $("#slip-prob");
    const oddsEl = $("#slip-odds");
    if (r.priced && r.priced.fair_parlay_odds) {
      state.slipFairOdds = r.priced.fair_parlay_odds;
      if (probEl) probEl.textContent = (r.priced.true_probability * 100).toFixed(1) + "%";
      if (oddsEl) oddsEl.textContent = fmtOdds(r.priced.fair_parlay_odds);
    } else {
      state.slipFairOdds = null;
      if (probEl) probEl.textContent = "-";
      if (oddsEl) oddsEl.textContent = "-";
    }
    updateSlipCalculations();
  } catch (e) {
    /* ignore polling/network glitch */
  }
}

export async function clearSlipAction(onDetailUpdate) {
  try {
    await clearSlip(state.sessionId);
    state.slipFairOdds = null;
    await refreshSlip(onDetailUpdate);
  } catch (e) {
    toast(state.lang === "es" ? "Error al vaciar boleto" : "Could not clear slip");
  }
}

export async function placePaperBetAction(stake, onDetailUpdate, syncPanelPositions) {
  if (!(stake > 0)) {
    return toast(state.lang === "es" ? "Ingresa un monto primero" : "Enter a stake first");
  }
  try {
    await placePaperBet(state.sessionId, stake);
    toast(state.lang === "es" ? "Apuesta simulada realizada" : "Paper bet placed");
    const slipPanel = $("#slip-panel");
    if (slipPanel) slipPanel.classList.remove("open");
    if (syncPanelPositions) syncPanelPositions();
    state.slipFairOdds = null;
    await refreshSlip(onDetailUpdate);
    await refreshBankrollDisplay();
    if (onDetailUpdate) onDetailUpdate();
  } catch (e) {
    toast(state.lang === "es" ? "Error al realizar la apuesta" : "Could not place that bet");
  }
}

export async function refreshBankrollDisplay() {
  try {
    const summary = await getBankrollSummary();
    if (summary && summary.current_bankroll != null) {
      state.bankrollBase = summary.base_bankroll;
      const bankrollAmt = $("#bankroll-amt");
      if (bankrollAmt) {
        bankrollAmt.textContent = Number(summary.current_bankroll).toFixed(2);
      }
    }
  } catch (e) {
    try {
      const [settings, bets] = await Promise.all([getSettings(), getBets()]);
      state.bankrollBase = settings.bankroll;
      const settledPnl = bets.filter((b) => b.status !== "open").reduce((a, b) => a + b.pnl, 0);
      const openStake = bets.filter((b) => b.status === "open").reduce((a, b) => a + b.stake, 0);
      const bankrollAmt = $("#bankroll-amt");
      if (bankrollAmt) {
        bankrollAmt.textContent = (settings.bankroll + settledPnl - openStake).toFixed(2);
      }
    } catch (_) {}
  }
}

export async function deleteBetAction(betId, onRefreshModal) {
  try {
    await deleteBet(betId);
    toast(state.lang === "es" ? "Apuesta eliminada" : "Bet deleted");
    await refreshBankrollDisplay();
    if (onRefreshModal) await onRefreshModal();
  } catch (e) {
    toast(state.lang === "es" ? "Error al eliminar apuesta" : "Error deleting bet");
  }
}

export async function clearAllBetsAction(onRefreshModal) {
  const confirmMsg = I18N[state.lang]?.clear_history_confirm || "¿Estás seguro de que deseas vaciar todo el historial?";
  if (!confirm(confirmMsg)) return;
  try {
    await clearAllBets();
    toast(I18N[state.lang]?.history_cleared || "Historial vaciado");
    await refreshBankrollDisplay();
    if (onRefreshModal) await onRefreshModal();
  } catch (e) {
    toast(state.lang === "es" ? "Error al vaciar historial" : "Error clearing history");
  }
}
