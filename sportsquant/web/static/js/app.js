// SportsQuant - Main Application Orchestrator (ES Module Entrypoint)

import { state, $, $$, toast } from "./modules/state.js";
import {
  api,
  getEvents,
  getEvent,
  refreshEvents,
  getBets,
} from "./modules/api.js";
import {
  renderRail,
  renderDateFilter,
  renderCompFilter,
  renderMatchList,
  renderDetail,
  clearDetail,
  renderDetailLoading,
  renderListLoading,
  showLoadingBar,
  hideLoadingBar,
  showListMobile,
  showDetailMobile,
  renderBetsModal,
  applyTranslations,
  renderGroupsAndInfo,
} from "./modules/render.js";
import {
  isPicked,
  toggleSlip,
  refreshSlip,
  clearSlipAction,
  placePaperBetAction,
  refreshBankrollDisplay,
} from "./modules/slip.js";
import { wireChat, syncPanelPositions } from "./modules/chat.js";

// ---------------------------------------------------------------- Detail Helpers
function rerenderCurrentDetail() {
  if (state.detail) {
    renderGroupsAndInfo(
      state.detail,
      isPicked,
      handleToggleSlip,
      handleDetailRefresh
    );
  }
}

function handleToggleSlip(g, s, btn) {
  toggleSlip(g, s, btn, rerenderCurrentDetail);
}

async function handleDetailRefresh() {
  if (!state.selectedId) return;
  try {
    const d = await getEvent(state.selectedId);
    state.detailCache[state.selectedId] = d;
    renderDetail(d, isPicked, handleToggleSlip, handleDetailRefresh);
  } catch (e) {
    /* ignore transient polling errors */
  }
}

async function selectEvent(id) {
  state.selectedId = id;
  renderMatchList((matchId) => selectEvent(matchId));
  showDetailMobile();

  if (state.detailCache[id]) {
    renderDetail(state.detailCache[id], isPicked, handleToggleSlip, handleDetailRefresh);
  } else {
    const match = state.events.find((e) => e.id === id);
    const title = match ? `${match.home} vs ${match.away}` : "";
    renderDetailLoading(title);
    showLoadingBar();
  }

  try {
    state.prevFlat = {};
    const d = await getEvent(id);
    state.detailCache[id] = d;
    renderDetail(d, isPicked, handleToggleSlip, handleDetailRefresh);
  } catch (e) {
    if (!state.detailCache[id]) {
      toast(state.lang === "es" ? "No se pudo cargar el partido" : "Could not load match");
    }
  } finally {
    hideLoadingBar();
  }
}

async function handleSelectSport(sportId) {
  if (state.sport === sportId && state.events.length > 0) return;
  state.sport = sportId;
  localStorage.setItem("sq_sport", sportId);
  state.compFilter = null;
  state.dateFilter = "all";
  state.selectedId = null;
  state.events = [];
  renderRail();
  renderListLoading();
  clearDetail();
  await loadEvents(true);
  showListMobile();
}

// ---------------------------------------------------------------- Events Ingestion / Polling
async function loadEvents(isInitialOrForce) {
  if (document.hidden && !isInitialOrForce) return;

  if (isInitialOrForce || !state.events.length) {
    showLoadingBar();
    renderListLoading();
    const syncTxt = $("#sync-text");
    if (syncTxt) {
      syncTxt.textContent = state.lang === "es" ? "Sincronizando..." : "Syncing...";
    }
  }

  try {
    const evs = await getEvents(state.sport);
    const evsSig = JSON.stringify(evs.map((e) => [e.id, e.status, e.main_market]));
    const hasChanged = isInitialOrForce || state._lastEvsSig !== evsSig;
    state._lastEvsSig = evsSig;
    state.events = evs;

    if (hasChanged) {
      renderDateFilter(
        () => renderMatchList((id) => selectEvent(id)),
        handleManualRefresh
      );
      renderCompFilter(state.events, () => renderMatchList((id) => selectEvent(id)));
      renderMatchList((id) => selectEvent(id));
    }

    if (!isInitialOrForce && state.selectedId && state.events.some((e) => e.id === state.selectedId)) {
      return;
    }

    if (state.events.length > 0) {
      selectEvent(state.events[0].id);
    } else {
      clearDetail();
    }
  } catch (e) {
    toast(state.lang === "es" ? "No se pudo conectar al servidor" : "Could not reach the server");
  } finally {
    if (isInitialOrForce) hideLoadingBar();
    const syncTxt = $("#sync-text");
    if (syncTxt) {
      syncTxt.textContent = state.lang === "es" ? "Sincronizado" : "Synced";
    }
  }
}

async function handleManualRefresh(btn) {
  if (btn) btn.classList.add("spinning");
  const syncTxt = $("#sync-text");
  if (syncTxt) syncTxt.textContent = state.lang === "es" ? "Actualizando..." : "Syncing...";
  try {
    await refreshEvents();
    await loadEvents(true);
    toast(state.lang === "es" ? "Partidos recargados en tiempo real" : "Events reloaded");
  } catch (e) {
    toast(state.lang === "es" ? "Error al conectar con la API" : "Error connecting to API");
  } finally {
    if (btn) btn.classList.remove("spinning");
    if (syncTxt) syncTxt.textContent = state.lang === "es" ? "Sincronizado" : "Synced";
  }
}

function startPolling() {
  setInterval(() => {
    if (!document.hidden) loadEvents(false);
  }, 12000);
  setInterval(() => {
    if (state.selectedId && !document.hidden) handleDetailRefresh();
  }, 8000);
  setInterval(() => {
    if (!document.hidden) refreshBankrollDisplay();
  }, 30000);
}

// ---------------------------------------------------------------- Static Listeners Wiring
function wireStatic() {
  // Theme toggle
  const themeBtn = $("#theme-toggle");
  const currentTheme = localStorage.getItem("sportsquant_theme") || "dark";
  if (currentTheme === "light") {
    document.body.classList.add("light-theme");
    if (themeBtn) themeBtn.textContent = "🌙";
  } else {
    document.body.classList.remove("light-theme");
    if (themeBtn) themeBtn.textContent = "☀️";
  }
  if (themeBtn) {
    themeBtn.onclick = () => {
      const isLight = document.body.classList.toggle("light-theme");
      localStorage.setItem("sportsquant_theme", isLight ? "light" : "dark");
      themeBtn.textContent = isLight ? "🌙" : "☀️";
      toast(
        isLight
          ? state.lang === "es" ? "Tema claro activado" : "Light theme activated"
          : state.lang === "es" ? "Tema oscuro activado" : "Dark theme activated"
      );
    };
  }

  // Topbar refresh button
  const refreshBtn = $("#refresh-btn");
  if (refreshBtn) {
    refreshBtn.onclick = () => handleManualRefresh(refreshBtn);
  }

  // Language buttons
  $$(".lang-toggle button").forEach((b) => {
    b.classList.toggle("active", b.dataset.lang === state.lang);
    b.onclick = () => {
      state.lang = b.dataset.lang;
      localStorage.setItem("sq_lang", state.lang);
      $$(".lang-toggle button").forEach((x) => x.classList.toggle("active", x === b));
      applyTranslations(isPicked, handleToggleSlip, handleDetailRefresh);
    };
  });

  // Odds format buttons
  $$(".odds-toggle button").forEach((b) => {
    b.classList.toggle("active", b.dataset.fmt === state.oddsFmt);
    b.onclick = () => {
      state.oddsFmt = b.dataset.fmt;
      localStorage.setItem("sq_odds_fmt", state.oddsFmt);
      $$(".odds-toggle button").forEach((x) => x.classList.toggle("active", x === b));
      renderMatchList((id) => selectEvent(id));
      rerenderCurrentDetail();
      refreshSlip(rerenderCurrentDetail);
    };
  });

  // Slip FAB & actions
  const slipFab = $("#slip-fab");
  if (slipFab) {
    slipFab.onclick = () => {
      const slipPanel = $("#slip-panel");
      if (slipPanel) slipPanel.classList.toggle("open");
      syncPanelPositions();
    };
  }
  const slipClear = $("#slip-clear");
  if (slipClear) {
    slipClear.onclick = () => clearSlipAction(rerenderCurrentDetail);
  }
  const slipPlace = $("#slip-place");
  if (slipPlace) {
    slipPlace.onclick = () => {
      const stake = parseFloat($("#slip-stake")?.value || "0");
      placePaperBetAction(stake, rerenderCurrentDetail, syncPanelPositions);
    };
  }

  // Bets history modal
  const betsBtn = $("#bets-btn");
  const betsModalBg = $("#bets-modal-bg");
  const betsClose = $("#bets-close");
  if (betsBtn) {
    betsBtn.onclick = async () => {
      if (betsModalBg) betsModalBg.style.display = "block";
      try {
        const bets = await getBets();
        renderBetsModal(bets);
      } catch (e) {
        toast(state.lang === "es" ? "Error al cargar historial" : "Error loading history");
      }
    };
  }
  if (betsClose) {
    betsClose.onclick = () => {
      if (betsModalBg) betsModalBg.style.display = "none";
    };
  }
  if (betsModalBg) {
    betsModalBg.onclick = (e) => {
      if (e.target.id === "bets-modal-bg") betsModalBg.style.display = "none";
    };
  }

  // Search input filter
  const searchInput = $("#search-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      const q = e.target.value.trim().toLowerCase();
      if (!q) {
        renderMatchList((id) => selectEvent(id));
        return;
      }
      const prev = state.events;
      state.events = state.events.filter((ev) =>
        (ev.home + " " + ev.away + " " + ev.competition).toLowerCase().includes(q)
      );
      renderMatchList((id) => selectEvent(id));
      state.events = prev;
    });
  }

  // Sport rail selector
  renderRail(handleSelectSport);
}

function checkProtocol() {
  if (window.location.protocol === "file:") {
    const warn = $("#file-protocol-warning");
    if (warn) warn.style.display = "block";
  }
}

// ---------------------------------------------------------------- Initialization
async function init() {
  checkProtocol();
  wireStatic();
  wireChat(rerenderCurrentDetail);
  applyTranslations(isPicked, handleToggleSlip, handleDetailRefresh);

  try {
    const s = await api("/api/settings");
    state.bankrollBase = s.bankroll;
    const bankrollEl = $("#bankroll-amt");
    if (bankrollEl) bankrollEl.textContent = s.bankroll.toFixed(2);
  } catch (e) {
    /* fallback to default */
  }

  await loadEvents(true);
  await refreshSlip(rerenderCurrentDetail);
  await refreshBankrollDisplay();
  startPolling();
}

document.addEventListener("DOMContentLoaded", init);
