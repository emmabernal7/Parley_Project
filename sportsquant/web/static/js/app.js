// SportsQuant frontend with bilingual I18N support (ES / EN) & instant sport navigation.
(() => {
  "use strict";

  const I18N = {
    es: {
      paper_trading: "Simulación Paper",
      search_placeholder: "Buscar equipos o competencias...",
      reload_api: "Recargar API",
      paper_bankroll: "simulado",
      my_bets: "Mis apuestas simuladas",
      empty_detail: "Selecciona un partido a la izquierda para ver predicciones cuantitativas y cuotas justas en tiempo real.",
      no_matches: "No hay partidos disponibles en este momento. Prueba otra pestaña o regresa pronto.",
      todos: "Todos",
      hoy: "Hoy",
      manana: "Mañana 📅",
      recargar_api_chip: "🔄 Recargar API",
      bet_slip: "Boleto de apuestas",
      clear: "Vaciar",
      true_prob: "Probabilidad justa",
      fair_odds: "Cuotas estimadas",
      paper_stake: "Monto simulado",
      place_bet: "Realizar apuesta simulada",
      assistant_title: "Asistente Quant",
      ask_placeholder: "Pregunta sobre un partido, Over 3.5 carreras Tampa, cuotas...",
      prop_chip: "⚾ Over 3.5 carreras Tampa",
      carib_chip: "⚾ Béisbol del Caribe (LVBP/LIDOM)",
      value_bets_chip: "💎 Apuestas +EV",
      price_slip_chip: "📊 Analizar mi boleto",
      opinion_chip: "💡 Opinión de partido",
      loading_matches: "Cargando partidos y cuotas en tiempo real...",
      loading_sub: "Consultando APIs oficiales en directo",
      loading_markets: "Calculando modelos probabilísticos (Dixon-Coles, Poisson)...",
      loading_markets_sub: "Analizando alineaciones, abridores, árbitro y clima",
      tip_title: "Consejo Táctico",
      tip_body: "Haz clic en una cuota para agregarla a tu boleto. Haz clic derecho (o mantén presionado) en una cuota para ingresar el precio de tu casa de apuestas y buscar valor (+EV).",
      model_title: "Modelo Estadístico",
      method: "Método",
      exp_score: "Marcador esperado",
      exp_margin: "Margen esperado",
      exp_total: "Total esperado",
      odds_fmt_label: "Formato de cuotas",
      weather_title: "Clima al inicio",
      condition: "Condición",
      temp: "Temperatura",
      wind: "Viento",
      fitted_model: "MODELO ENTRENADO",
      low_confidence: "PRIOR BAJA CONFIANZA",
      demo_model: "MODELO DEMO",
      sports: {
        soccer: "Fútbol",
        basketball: "Baloncesto",
        american_football: "NFL",
        baseball: "Béisbol",
        hockey: "Hockey",
        tennis: "Tenis",
        volleyball: "Voleibol",
        mma: "MMA",
        motorsport: "F1",
        waterpolo: "Waterpolo"
      },
      tabs: {
        main: "Principal",
        sgm: "Múltiple Mismo Partido",
        goals: "Goles / Totales",
        asian: "Líneas Asiáticas",
        half: "Mitad",
        lines: "Líneas",
        specials: "Especiales",
        minute: "Mercados por Minuto"
      }
    },
    en: {
      paper_trading: "paper trading",
      search_placeholder: "Search teams or competitions...",
      reload_api: "Reload API",
      paper_bankroll: "paper",
      my_bets: "My paper bets",
      empty_detail: "Pick a match on the left to see live quantitative predictions and fair markets.",
      no_matches: "No matches right now for this sport. Try another tab, or check back soon.",
      todos: "All",
      hoy: "Today",
      manana: "Tomorrow 📅",
      recargar_api_chip: "🔄 Reload API",
      bet_slip: "Bet slip",
      clear: "Clear",
      true_prob: "True probability",
      fair_odds: "Fair odds",
      paper_stake: "Paper stake",
      place_bet: "Place paper bet",
      assistant_title: "Betting assistant",
      ask_placeholder: "Ask about a match, Over 3.5 runs Tampa Bay, parlay, Kelly...",
      value_bets_chip: "Value bets",
      price_slip_chip: "Price my slip",
      opinion_chip: "Match opinion",
      prop_chip: "Over 3.5 runs Tampa",
      carib_chip: "Caribbean Baseball (LVBP/LIDOM)",
      loading_matches: "Loading matches & real-time odds...",
      loading_sub: "Fetching official live feeds",
      loading_markets: "Calculating fair probabilities & markets...",
      loading_markets_sub: "Analyzing lineups, starters, referee and weather",
      tip_title: "Tip",
      tip_body: "Click a price to add it to your bet slip. Right-click (or long-press) a price to type in the odds your own sportsbook is offering - the assistant can then flag it as +EV.",
      model_title: "Model",
      method: "Method",
      exp_score: "Expected score",
      exp_margin: "Expected margin",
      exp_total: "Expected total",
      odds_fmt_label: "Odds format",
      weather_title: "Weather at kickoff",
      condition: "Condition",
      temp: "Temp",
      wind: "Wind",
      fitted_model: "FITTED MODEL",
      low_confidence: "LOW-CONFIDENCE PRIOR",
      demo_model: "DEMO MODEL",
      sports: {
        soccer: "Soccer",
        basketball: "Basketball",
        american_football: "NFL",
        baseball: "Baseball",
        hockey: "Hockey",
        tennis: "Tennis",
        volleyball: "Volleyball",
        mma: "MMA",
        motorsport: "F1",
        waterpolo: "Water Polo"
      },
      tabs: {
        main: "Main",
        sgm: "Same Game Multi",
        goals: "Goals",
        asian: "Asian Lines",
        half: "Half",
        lines: "Lines",
        specials: "Specials",
        minute: "Minute Markets"
      }
    }
  };

  const $ = (sel, el) => (el || document).querySelector(sel);
  const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
  const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };

  function uid() {
    return "s_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  const state = {
    sessionId: localStorage.getItem("sq_session") || (() => { const v = uid(); localStorage.setItem("sq_session", v); return v; })(),
    oddsFmt: localStorage.getItem("sq_odds_fmt") || "pct",
    lang: localStorage.getItem("sq_lang") || "es",
    sport: localStorage.getItem("sq_sport") || "soccer",
    dateFilter: "all",
    compFilter: null,
    allEvents: [],
    events: [],
    selectedId: null,
    detail: null,
    detailCache: {},
    prevFlat: {},
    activeTab: "main",
    slipLegs: [],
    bankrollBase: 1000,
  };

  function getSports() {
    const t = I18N[state.lang].sports;
    return [
      { id: "soccer", ic: "⚽", label: t.soccer },
      { id: "basketball", ic: "🏀", label: t.basketball },
      { id: "american_football", ic: "🏈", label: t.american_football },
      { id: "baseball", ic: "⚾", label: t.baseball },
      { id: "hockey", ic: "🏒", label: t.hockey },
      { id: "tennis", ic: "🎾", label: t.tennis },
      { id: "volleyball", ic: "🏐", label: t.volleyball },
      { id: "mma", ic: "🥊", label: t.mma },
      { id: "motorsport", ic: "🏎️", label: t.motorsport },
      { id: "waterpolo", ic: "🤽", label: t.waterpolo },
    ];
  }

  function getTabOrder() {
    const t = I18N[state.lang].tabs;
    return [
      ["main", t.main], ["sgm", t.sgm], ["goals", t.goals], ["asian", t.asian],
      ["half", t.half], ["lines", t.lines], ["specials", t.specials], ["minute", t.minute],
    ];
  }

  // ---------------------------------------------------------------- formatting
  function fmtOdds(o) {
    if (o == null || !isFinite(o)) return "-";
    if (o < 10) return o.toFixed(2);
    if (o < 100) return o.toFixed(1);
    return Math.round(o).toString();
  }
  function fmtSel(sel) {
    if (!sel) return "-";
    if (state.oddsFmt === "pct") {
      if (sel.prob != null && isFinite(sel.prob)) {
        return (sel.prob * 100).toFixed(1) + "%";
      } else if (sel.odds != null && isFinite(sel.odds) && sel.odds > 0) {
        return ((1 / sel.odds) * 100).toFixed(1) + "%";
      }
      return "-";
    }
    return fmtOdds(sel.odds);
  }
  function fmtClock(ev) {
    if (ev.status === "finished") return "FT";
    if (ev.status === "scheduled") {
      const d = new Date(ev.kickoff);
      return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + "\n" + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    const c = ev.clock || {};
    if (c.phase === "ht") return "HT";
    if (c.minute != null) return Math.min(90, Math.round(c.minute)) + (c.minute > 90 ? "+" : "") + "'";
    if (c.elapsed != null) return Math.round(c.elapsed * 100) + "%";
    if (c.inning) return (c.half === "top" ? "T" : "B") + c.inning;
    return "LIVE";
  }
  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.classList.add("show");
    clearTimeout(toast._h); toast._h = setTimeout(() => t.classList.remove("show"), 2200);
  }

  // ---------------------------------------------------------------- API
  async function api(path, opts) {
    const r = await fetch(path, opts);
    if (!r.ok) throw new Error("API " + path + " -> " + r.status);
    return r.json();
  }
  const getEvents = (sport) => api("/api/events" + (sport ? "?sport=" + encodeURIComponent(sport) : ""));
  const getEvent = (id) => api("/api/event/" + encodeURIComponent(id));
  const setUserOdds = (id, key, odds) => api("/api/event/" + encodeURIComponent(id) + "/odds", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key, odds }),
  });
  const postJSON = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

  // ---------------------------------------------------------------- loading indicators
  function showLoadingBar() {
    const b = $("#top-progress-bar");
    if (b) b.classList.add("active");
  }
  function hideLoadingBar() {
    const b = $("#top-progress-bar");
    if (b) b.classList.remove("active");
  }

  function renderListLoading() {
    const list = $("#match-list");
    if (!list) return;
    const t = I18N[state.lang] || I18N.es;
    list.innerHTML = `
      <div class="loading-container">
        <div class="glow-spinner"></div>
        <div class="loading-title">${t.loading_matches || "Cargando partidos y cuotas en tiempo real..."}</div>
        <div class="loading-sub">${t.loading_sub || "Consultando APIs oficiales en directo"}</div>
      </div>
      <div class="skeleton-list">
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
      </div>
    `;
  }

  function renderDetailLoading(title) {
    const cd = $("#col-detail");
    if (!cd) return;
    const t = I18N[state.lang] || I18N.es;
    cd.innerHTML = `
      <div class="loading-container" style="min-height:360px;">
        <div class="glow-spinner lg"></div>
        <div class="loading-title">${title ? title + " &bull; " : ""}${t.loading_markets || "Calculando probabilidades y mercados en vivo..."}</div>
        <div class="loading-sub">${t.loading_markets_sub || "Analizando alineaciones, abridores, árbitro y clima"}</div>
      </div>
    `;
  }

  // ---------------------------------------------------------------- rail
  function filterAndRenderSport(keepSelection = false) {
    state.events = state.allEvents.filter((e) => e.sport === state.sport);
    renderDateFilter();
    renderCompFilter(state.events);
    renderMatchList();

    if (keepSelection && state.selectedId && state.events.some((e) => e.id === state.selectedId)) {
      return;
    }

    if (state.events.length > 0) {
      selectEvent(state.events[0].id);
    } else {
      clearDetail();
    }
  }

  function renderRail() {
    const rail = $("#rail"); rail.innerHTML = "";
    getSports().forEach((s) => {
      const b = el("button", "rail-item" + (s.id === state.sport ? " active" : ""),
        `<span class="ic">${s.ic}</span><span>${s.label}</span>`);
      b.onclick = () => {
        if (state.sport === s.id && state.events.length > 0) return;
        state.sport = s.id;
        localStorage.setItem("sq_sport", s.id);
        state.compFilter = null;
        state.dateFilter = "all";
        state.selectedId = null;
        renderRail();
        renderListLoading();
        loadEvents(true);
        showListMobile();
      };
      rail.appendChild(b);
    });
  }

  // ---------------------------------------------------------------- match list
  function competitionsOf(events) {
    const seen = new Map();
    events.forEach((e) => seen.set(e.competition, (seen.get(e.competition) || 0) + 1));
    return Array.from(seen.entries()).sort((a, b) => b[1] - a[1]);
  }

  function isSameDay(d1, d2) {
    return d1.getFullYear() === d2.getFullYear() &&
           d1.getMonth() === d2.getMonth() &&
           d1.getDate() === d2.getDate();
  }

  function renderDateFilter() {
    const box = $("#date-filter");
    if (!box) return;
    box.innerHTML = "";
    const t = I18N[state.lang];
    const options = [
      { id: "all", label: t.todos },
      { id: "today", label: t.hoy },
      { id: "tomorrow", label: t.manana },
    ];
    options.forEach((opt) => {
      const btn = el("button", "chip" + (state.dateFilter === opt.id ? " active" : ""), opt.label);
      btn.onclick = () => {
        state.dateFilter = opt.id;
        renderDateFilter();
        renderMatchList();
      };
      box.appendChild(btn);
    });
    const refBtn = el("button", "chip chip-refresh", t.recargar_api_chip);
    refBtn.onclick = async () => {
      refBtn.classList.add("spinning");
      try {
        await postJSON("/api/events/refresh", {});
        await loadEvents(true);
        toast(state.lang === "es" ? "Partidos recargados desde la API" : "Events reloaded from API");
      } catch (e) {
        toast(state.lang === "es" ? "Error al conectar con la API" : "Error connecting to API");
      } finally {
        refBtn.classList.remove("spinning");
      }
    };
    box.appendChild(refBtn);
  }

  function renderCompFilter(events) {
    const box = $("#comp-filter"); box.innerHTML = "";
    const all = el("button", "chip" + (state.compFilter === null ? " active" : ""), state.lang === "es" ? "Todas" : "All");
    all.onclick = () => { state.compFilter = null; renderCompFilter(events); renderMatchList(); };
    box.appendChild(all);
    competitionsOf(events).forEach(([name, n]) => {
      const c = el("button", "chip" + (state.compFilter === name ? " active" : ""), `${name} (${n})`);
      c.onclick = () => { state.compFilter = name; renderCompFilter(events); renderMatchList(); };
      box.appendChild(c);
    });
  }

  function miniOddsFor(ev) {
    if (ev.main_market && ev.main_market.selections) {
      return ev.main_market.selections;
    }
    return null;
  }

  function renderMatchList() {
    const list = $("#match-list");
    let evs = state.events;
    const t = I18N[state.lang];

    if (state.dateFilter === "today") {
      const now = new Date();
      evs = evs.filter((e) => isSameDay(new Date(e.kickoff), now));
    } else if (state.dateFilter === "tomorrow") {
      const tom = new Date();
      tom.setDate(tom.getDate() + 1);
      evs = evs.filter((e) => isSameDay(new Date(e.kickoff), tom));
    }

    if (state.compFilter) evs = evs.filter((e) => e.competition === state.compFilter);
    if (!evs.length) {
      list.innerHTML = "";
      list.appendChild(el("div", "", `<div id='empty-list'>${t.no_matches}</div>`));
      return;
    }

    function cleanCompBadge(comp) {
      if (!comp) return "COMPETENCIA";
      if (comp.includes("LVBP")) return "🇻🇪 LVBP";
      if (comp.includes("LIDOM")) return "🇩🇴 LIDOM";
      if (comp.includes("LMP")) return "🇲🇽 LMP";
      if (comp.includes("LBPRC")) return "🇵🇷 LBPRC";
      if (comp.includes("Serie del Caribe")) return "🌴 Serie del Caribe";
      if (comp.includes("World Baseball Classic") || comp.includes("WBC")) return "⚾ Clásico Mundial (WBC)";
      if (comp.includes("Major League Baseball") || comp.includes("MLB")) return "⚾ MLB";
      if (comp.includes("Premier League")) return "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League";
      if (comp.includes("La Liga")) return "🇪🇸 La Liga";
      if (comp.includes("Serie A")) return "🇮🇹 Serie A";
      if (comp.includes("Bundesliga")) return "🇩🇪 Bundesliga";
      if (comp.includes("Ligue 1")) return "🇫🇷 Ligue 1";
      if (comp.includes("NBA")) return "🏀 NBA";
      if (comp.includes("EuroLeague")) return "🏀 EuroLeague";
      if (comp.includes("NFL")) return "🏈 NFL";
      if (comp.includes("NHL")) return "🏒 NHL";
      return comp.length > 24 ? comp.slice(0, 22) + "…" : comp;
    }

    function fmtScheduleTime(ev) {
      if (ev.status === "live") {
        return `<span class="live-dot"></span> EN VIVO ${fmtClock(ev)}`;
      }
      if (ev.status === "finished") {
        return "Final";
      }
      const d = new Date(ev.kickoff);
      const now = new Date();
      const isToday = d.getDate() === now.getDate() && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
      const tom = new Date(now);
      tom.setDate(tom.getDate() + 1);
      const isTomorrow = d.getDate() === tom.getDate() && d.getMonth() === tom.getMonth() && d.getFullYear() === tom.getFullYear();
      const timeStr = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      if (isToday) return `🕒 Hoy ${timeStr}`;
      if (isTomorrow) return `🕒 Mañana ${timeStr}`;
      const dateStr = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      return `📅 ${dateStr} ${timeStr}`;
    }

    function fmtVenueText(ev) {
      if (ev.venue && (ev.venue.name || ev.venue.city)) {
        const parts = [];
        if (ev.venue.name) parts.push(ev.venue.name);
        if (ev.venue.city) parts.push(ev.venue.city);
        return parts.join(", ");
      }
      return "Estadio Principal";
    }

    list.innerHTML = "";
    evs.forEach((e) => {
      const row = el("div", "match-row" + (e.id === state.selectedId ? " selected" : ""));
      const isLive = e.status === "live";
      const timeHtml = fmtScheduleTime(e);
      const compBadge = cleanCompBadge(e.competition);
      const venueTxt = fmtVenueText(e);

      row.innerHTML = `
        <div class="mr-header">
          <span class="mr-comp-badge">${compBadge}</span>
          <span class="mr-time-badge ${isLive ? 'live' : ''}">${timeHtml}</span>
        </div>
        <div class="mr-teams-block">
          <div class="mr-team-line home">
            <span class="t-name">${e.home}</span>
            <span class="t-score">${e.status === "scheduled" ? "" : e.score[0]}</span>
          </div>
          <div class="mr-team-line away">
            <span class="t-name">${e.away}</span>
            <span class="t-score">${e.status === "scheduled" ? "" : e.score[1]}</span>
          </div>
        </div>
        <div class="mr-footer">
          <span class="venue-txt">📍 ${venueTxt}</span>
        </div>
      `;

      row.onclick = () => selectEvent(e.id);
      list.appendChild(row);
    });
  }

  function translateGroupName(name) {
    if (state.lang !== "es" || !name) return name;
    if (name === "Moneyline") return "Ganador del Partido (Moneyline)";
    if (name === "Moneyline (incl. OT)") return "Ganador (incl. Prórroga / Extras)";
    if (name === "Match Winner") return "Ganador del Partido";
    if (name === "1x2") return "Resultado Final (1X2)";
    if (name.startsWith("Total Runs ")) return name.replace("Total Runs ", "Total Carreras (Más/Menos) ");
    if (name.startsWith("Total Goals ")) return name.replace("Total Goals ", "Total Goles (Más/Menos) ");
    if (name.startsWith("Run Line ")) return name.replace("Run Line ", "Línea de Carreras (Run Line) ");
    if (name.startsWith("Puck Line ")) return name.replace("Puck Line ", "Línea de Puck ");
    if (name.startsWith("Set Handicap ")) return name.replace("Set Handicap ", "Hándicap de Sets ");
    if (name === "Both Teams to Score") return "Ambos Equipos Anotan";
    if (name === "Double Chance") return "Doble Oportunidad";
    if (name === "Draw No Bet") return "Empate Apuesta No Válida (DNB)";
    if (name === "Half Time / Full Time") return "Descanso / Final (HT/FT)";
    if (name === "First 5 Innings Result") return "Resultado Primeras 5 Entradas (F5)";
    if (name === "60 Minutes Result") return "Resultado Tiempo Regular (60 Min)";
    if (name === "Set Betting") return "Marcador Exacto de Sets";
    if (name.startsWith("Total Sets ")) return name.replace("Total Sets ", "Total de Sets ");
    if (name.startsWith("Total Games ")) return name.replace("Total Games ", "Total de Juegos ");
    if (name.includes(" Total ")) return name.replace(" Total ", " Total ");
    return name;
  }

  function translateLabel(lbl) {
    if (state.lang !== "es" || !lbl) return lbl;
    if (lbl === "Draw" || lbl === "Tie") return "Empate";
    if (lbl === "Over") return "Más de";
    if (lbl === "Under") return "Menos de";
    if (lbl.startsWith("Over ")) return lbl.replace("Over ", "Más de ");
    if (lbl.startsWith("Under ")) return lbl.replace("Under ", "Menos de ");
    if (lbl === "Yes") return "Sí";
    if (lbl === "No") return "No";
    if (lbl.includes(" or Draw")) return lbl.replace(" or Draw", " o Empate");
    if (lbl.startsWith("Draw or ")) return lbl.replace("Draw or ", "Empate o ");
    return lbl;
  }

  // ---------------------------------------------------------------- detail
  function groupKindClass(g) {
    const n = g.selections.length;
    if (g.kind === "3way") return "k-3";
    if (g.kind === "2way") return "k-2";
    return n <= 4 ? "k-2" : "k-multi";
  }

  function isPicked(gid, sid) {
    return state.slipLegs.some((l) => l.event_id === state.selectedId && l.key === gid + ":" + sid);
  }

  function renderGroup(g) {
    const card = el("div", "group-card");
    const head = el("div", "group-head");
    head.innerHTML = `<span class="name">${translateGroupName(g.name)}</span>` + (g.note ? `<span class="note">${g.note}</span>` : "");
    card.appendChild(head);
    const sels = el("div", "group-sels " + groupKindClass(g));
    g.selections.forEach((s) => {
      const btn = el("button", "sel-btn" + (isPicked(g.id, s.id) ? " picked" : ""));
      btn.innerHTML = `<span class="sel-label">${translateLabel(s.label)}</span><span class="sel-odds num">${fmtSel(s)}</span>`;
      btn.dataset.flatKey = g.id + ":" + s.id;
      btn.onclick = () => toggleSlip(g, s, btn);
      btn.oncontextmenu = (ev) => { ev.preventDefault(); editUserOdds(g, s); };
      sels.appendChild(btn);
    });
    card.appendChild(sels);
    return card;
  }

  async function editUserOdds(g, s) {
    const cur = s.user_odds != null ? s.user_odds : "";
    const promptMsg = state.lang === "es"
      ? `Cuota de tu casa de apuestas para "${s.label}" (${g.name}) - cuota decimal, blanco para borrar:`
      : `Your sportsbook price for "${s.label}" (${g.name}) - decimal odds, blank to clear:`;
    const val = prompt(promptMsg, cur);
    if (val === null) return;
    const num = val.trim() === "" ? null : parseFloat(val);
    try {
      await setUserOdds(state.selectedId, g.id + ":" + s.id, num);
      toast(num == null ? (state.lang === "es" ? "Cuota borrada" : "Cleared price") : (state.lang === "es" ? "Cuota guardada - buscando valor" : "Saved price"));
      await refreshDetail();
    } catch (e) { toast(state.lang === "es" ? "Error al guardar la cuota" : "Could not save that price"); }
  }

  function renderTabs(groups) {
    const present = new Set(groups.map((g) => g.tab));
    const bar = $("#market-tabs"); bar.innerHTML = "";
    const order = getTabOrder().filter(([id]) => present.has(id));
    if (!order.some(([id]) => id === state.activeTab)) state.activeTab = order.length ? order[0][0] : "main";
    order.forEach(([id, label]) => {
      const b = el("button", "mtab" + (id === state.activeTab ? " active" : ""), label);
      b.onclick = () => { state.activeTab = id; renderGroupsAndInfo(state.detail); };
      bar.appendChild(b);
    });
  }

  function renderHeader(d) {
    const t = I18N[state.lang];
    const ev = d.event;
    const box = $("#detail-header");
    const conf = d.info.confidence || "ok";
    const confCls = conf === "ok" ? "conf-ok" : conf === "demo" ? "conf-demo" : "conf-low";
    const badgeText = conf === "demo" ? t.demo_model : conf === "ok" ? t.fitted_model : t.low_confidence;
    box.innerHTML = `
      <div class="dh-top"><button class="back-btn" id="back-btn">‹ Matches</button><span>${ev.competition}</span></div>
      <div class="dh-teams">
        <div class="dh-team home">${ev.home}</div>
        <div class="dh-score">${ev.status === "scheduled" ? "vs" : ev.score[0] + " - " + ev.score[1]}</div>
        <div class="dh-team away">${ev.away}</div>
      </div>
      <div class="dh-clock ${ev.status}">${ev.status === "live" ? "● LIVE - " + fmtClock(ev) : ev.status === "finished" ? "Full time" : "Inicio: " + new Date(ev.kickoff).toLocaleString()}</div>
      <div class="dh-meta">
        <span class="confidence-badge ${confCls}">${badgeText}</span>
        ${d.referee ? `<span>🧑‍⚖️ ${d.referee}</span>` : ""}
        ${d.venue && d.venue.name ? `<span>📍 ${d.venue.name}</span>` : ""}
      </div>`;
    $("#back-btn").onclick = showListMobile;
  }

  function renderInfoCol(d) {
    const t = I18N[state.lang];
    const box = $("#info-col"); box.innerHTML = "";
    const model = el("div", "info-card");
    model.innerHTML = `<h4>${t.model_title}</h4>
      <div class="info-row"><span class="k">${t.method}</span><span class="v" style="text-align:right;max-width:60%">${d.info.model || "-"}</span></div>
      ${d.info.expected_final ? `<div class="info-row"><span class="k">${t.exp_score}</span><span class="v num">${d.info.expected_final[0].toFixed(2)} - ${d.info.expected_final[1].toFixed(2)}</span></div>` : ""}
      ${d.info.expected_margin != null ? `<div class="info-row"><span class="k">${t.exp_margin}</span><span class="v num">${d.info.expected_margin.toFixed(1)}</span></div>` : ""}
      ${d.info.expected_total != null ? `<div class="info-row"><span class="k">${t.exp_total}</span><span class="v num">${d.info.expected_total.toFixed(1)}</span></div>` : ""}
      <div class="info-row"><span class="k">${t.odds_fmt_label}</span><span class="v">${state.oddsFmt === "pct" ? "% Probabilidad" : "Cuota decimal"}</span></div>`;
    box.appendChild(model);

    if (d.weather) {
      const w = el("div", "info-card");
      w.innerHTML = `<h4>${t.weather_title}</h4>
        <div class="info-row"><span class="k">${t.condition}</span><span class="v">${d.weather.condition}</span></div>
        <div class="info-row"><span class="k">${t.temp}</span><span class="v num">${d.weather.temp_c}°C</span></div>
        <div class="info-row"><span class="k">${t.wind}</span><span class="v num">${d.weather.wind_kmh} km/h</span></div>`;
      box.appendChild(w);
    }
    const help = el("div", "info-card");
    help.innerHTML = `<h4>${t.tip_title}</h4><div style="font-size:12px;color:var(--text-dim);line-height:1.5">${t.tip_body}</div>`;
    box.appendChild(help);
  }

  function flashChanges(groups) {
    const flat = {};
    groups.forEach((g) => g.selections.forEach((s) => { flat[g.id + ":" + s.id] = s.odds; }));
    Object.keys(flat).forEach((k) => {
      const prev = state.prevFlat[k];
      if (prev != null && Math.abs(prev - flat[k]) > 1e-6) {
        const btn = document.querySelector(`.sel-btn[data-flat-key="${CSS.escape(k)}"]`);
        if (btn) { btn.classList.remove("flash-up", "flash-down"); void btn.offsetWidth; btn.classList.add(flat[k] > prev ? "flash-up" : "flash-down"); }
      }
    });
    state.prevFlat = flat;
  }

  function renderGroupsAndInfo(d) {
    renderTabs(d.groups);
    const col = $("#groups-col"); col.innerHTML = "";
    d.groups.filter((g) => g.tab === state.activeTab).forEach((g) => col.appendChild(renderGroup(g)));
    renderInfoCol(d);
    flashChanges(d.groups);
  }

  function renderDetail(d) {
    state.detail = d;
    $("#empty-detail") && ($("#empty-detail").style.display = "none");
    let wrap = $("#detail-wrap");
    if (!wrap) {
      const cd = $("#col-detail"); cd.innerHTML = "";
      wrap = el("div", "", ""); wrap.id = "detail-wrap"; wrap.style.display = "contents";
      cd.innerHTML = `<div id="detail-header"></div><div id="market-tabs"></div><div id="market-body"><div id="groups-col"></div><div id="info-col"></div></div>`;
    }
    renderHeader(d);
    renderGroupsAndInfo(d);
  }

  async function refreshDetail() {
    if (!state.selectedId) return;
    try {
      const d = await getEvent(state.selectedId);
      renderDetail(d);
    } catch (e) { /* ignore transient polling errors */ }
  }

  async function selectEvent(id) {
    state.selectedId = id;
    renderMatchList();
    showDetailMobile();

    if (state.detailCache[id]) {
      renderDetail(state.detailCache[id]);
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
      renderDetail(d);
    } catch (e) {
      if (!state.detailCache[id]) {
        toast(state.lang === "es" ? "No se pudo cargar el partido" : "Could not load match");
      }
    } finally {
      hideLoadingBar();
    }
  }

  // ---------------------------------------------------------------- slip
  async function toggleSlip(g, s, btn) {
    const key = g.id + ":" + s.id;
    const picked = isPicked(g.id, s.id);
    try {
      if (picked) {
        await postJSON("/api/slip/remove", { session_id: state.sessionId, event_id: state.selectedId, key });
      } else {
        await postJSON("/api/slip/add", { session_id: state.sessionId, event_id: state.selectedId, key });
      }
      btn.classList.toggle("picked");
      await refreshSlip();
    } catch (e) { toast("Could not update slip"); }
  }

  async function refreshSlip() {
    try {
      const r = await api("/api/slip?session_id=" + encodeURIComponent(state.sessionId));
      state.slipLegs = r.legs;
      $("#slip-count").textContent = r.legs.length;
      $("#slip-fab").style.display = r.legs.length ? "flex" : "none";
      $("#chat-fab").classList.toggle("has-slip", r.legs.length > 0);
      const legBox = $("#slip-legs"); legBox.innerHTML = "";
      (r.priced && r.priced.legs ? r.priced.legs : []).forEach((l, i) => {
        const leg = r.legs[i];
        const row = el("div", "slip-leg");
        row.innerHTML = `<div class="top"><span class="sel">${l.selection}</span><button class="rm">✕</button></div>
          <div class="ev">${l.event} - ${l.market} - ${(l.prob * 100).toFixed(1)}%</div>`;
        row.querySelector(".rm").onclick = async () => {
          await postJSON("/api/slip/remove", { session_id: state.sessionId, event_id: leg.event_id, key: leg.key });
          await refreshSlip();
          if (state.detail && leg.event_id === state.selectedId) renderGroupsAndInfo(state.detail);
        };
        legBox.appendChild(row);
      });
      if (r.priced && r.priced.fair_parlay_odds) {
        $("#slip-prob").textContent = (r.priced.true_probability * 100).toFixed(1) + "%";
        $("#slip-odds").textContent = fmtOdds(r.priced.fair_parlay_odds);
      } else { $("#slip-prob").textContent = "-"; $("#slip-odds").textContent = "-"; }
    } catch (e) { /* ignore */ }
  }

  // ---------------------------------------------------------------- bets
  async function refreshBankrollDisplay() {
    try {
      const [settings, bets] = await Promise.all([api("/api/settings"), api("/api/bets")]);
      state.bankrollBase = settings.bankroll;
      const settledPnl = bets.filter((b) => b.status !== "open").reduce((a, b) => a + b.pnl, 0);
      const openStake = bets.filter((b) => b.status === "open").reduce((a, b) => a + b.stake, 0);
      $("#bankroll-amt").textContent = (settings.bankroll + settledPnl - openStake).toFixed(2);
    } catch (e) { /* ignore */ }
  }

  async function renderBetsModal() {
    const bets = await api("/api/bets");
    const box = $("#bets-list");
    if (!bets.length) { box.innerHTML = `<p style='color:var(--text-faint)'>${state.lang === "es" ? "Sin apuestas simuladas aún." : "No paper bets yet."}</p>`; return; }
    box.innerHTML = "";
    bets.forEach((b) => {
      const row = el("div", "slip-leg");
      const statusColor = b.status === "won" ? "var(--teal)" : b.status === "lost" ? "var(--coral)" : "var(--text-dim)";
      row.innerHTML = `<div class="top"><span class="sel">Monto ${b.stake.toFixed(2)} - <span style="color:${statusColor}">${b.status.toUpperCase()}</span></span>
        <span class="num" style="color:${b.pnl > 0 ? "var(--teal)" : b.pnl < 0 ? "var(--coral)" : "var(--text-dim)"}">${b.pnl > 0 ? "+" : ""}${b.pnl.toFixed(2)}</span></div>
        <div class="ev">${b.legs.map((l) => l.label || l.key).join(" · ")}</div>`;
      box.appendChild(row);
    });
  }

  // ---------------------------------------------------------------- chat
  function addMsg(text, who) {
    const box = $("#chat-msgs");
    const m = el("div", "msg " + who, text.replace(/\n/g, "<br>"));
    box.appendChild(m); box.scrollTop = box.scrollHeight;
  }
  async function sendChat(text) {
    if (!text.trim()) return;
    addMsg(text, "user");
    $("#chat-input").value = "";
    const thinking = el("div", "msg bot", "…"); $("#chat-msgs").appendChild(thinking);
    try {
      const r = await postJSON("/api/chat", { session_id: state.sessionId, message: text });
      thinking.textContent = r.reply;
    } catch (e) { thinking.textContent = state.lang === "es" ? "Error al conectar con el asistente." : "Error reaching assistant."; }
    $("#chat-msgs").scrollTop = $("#chat-msgs").scrollHeight;
    refreshSlip();
  }

  function syncPanelPositions() {
    const bothOpen = $("#slip-panel").classList.contains("open") && $("#chat-panel").classList.contains("open");
    $("#chat-panel").classList.toggle("shift-left", bothOpen);
  }

  // ---------------------------------------------------------------- i18n applier
  function applyTranslations() {
    const t = I18N[state.lang];
    const tagPaper = $("#tag-paper"); if (tagPaper) tagPaper.textContent = t.paper_trading;
    const searchInput = $("#search-input"); if (searchInput) searchInput.placeholder = t.search_placeholder;
    const txtReload = $("#txt-reload"); if (txtReload) txtReload.textContent = t.reload_api;
    const lblBankroll = $("#lbl-bankroll"); if (lblBankroll) lblBankroll.textContent = t.paper_bankroll;

    const slipHead = $("#slip-panel .slip-head span"); if (slipHead) slipHead.textContent = t.bet_slip;
    const slipClear = $("#slip-clear"); if (slipClear) slipClear.textContent = t.clear;
    const slipFab = $("#slip-fab span"); if (slipFab) slipFab.textContent = t.bet_slip;
    const slipRows = $$("#slip-panel .slip-foot .row span:first-child");
    if (slipRows[0]) slipRows[0].textContent = t.true_prob;
    if (slipRows[1]) slipRows[1].textContent = t.fair_odds;
    const slipStake = $("#slip-stake"); if (slipStake) slipStake.placeholder = t.paper_stake;
    const slipPlace = $("#slip-place"); if (slipPlace) slipPlace.textContent = t.place_bet;

    const chatHead = $("#chat-panel .chat-head .title"); if (chatHead) chatHead.innerHTML = `<span class="dot"></span> ${t.assistant_title}`;
    const chatInput = $("#chat-input"); if (chatInput) chatInput.placeholder = t.ask_placeholder;
    const sugBtns = $$(".chat-suggestions button");
    if (sugBtns[0]) { sugBtns[0].textContent = t.prop_chip; sugBtns[0].dataset.q = state.lang === "es" ? "Over 3.5 carreras Tampa Bay vs Guardians" : "Over 3.5 runs Tampa Bay vs Guardians"; }
    if (sugBtns[1]) { sugBtns[1].textContent = t.carib_chip; sugBtns[1].dataset.q = state.lang === "es" ? "Over 4.5 carreras Magallanes vs Caribes" : "Over 4.5 runs Magallanes vs Caribes"; }
    if (sugBtns[2]) { sugBtns[2].textContent = t.value_bets_chip; sugBtns[2].dataset.q = state.lang === "es" ? "apuestas de valor" : "value bets"; }
    if (sugBtns[3]) { sugBtns[3].textContent = t.price_slip_chip; sugBtns[3].dataset.q = state.lang === "es" ? "analizar mi boleto" : "price my slip"; }

    renderRail();
    renderDateFilter();
    renderCompFilter(state.events);
    renderMatchList();
    if (state.detail) renderGroupsAndInfo(state.detail);
  }

  // ---------------------------------------------------------------- mobile helpers
  function showListMobile() { $("#col-list").classList.remove("hidden-mobile"); $("#col-detail").classList.add("hidden-mobile"); }
  function showDetailMobile() { $("#col-list").classList.add("hidden-mobile"); $("#col-detail").classList.remove("hidden-mobile"); }

  function clearDetail() {
    state.selectedId = null;
    state.detail = null;
    const t = I18N[state.lang];
    const cd = $("#col-detail");
    if (cd) {
      cd.innerHTML = `<div id="empty-detail" class="empty-state">${t.empty_detail}</div>`;
    }
  }

  // ---------------------------------------------------------------- polling
  async function loadEvents(isInitialOrForce) {
    if (isInitialOrForce || !state.events.length) {
      showLoadingBar();
      renderListLoading();
      const syncTxt = $("#sync-text");
      if (syncTxt) syncTxt.textContent = state.lang === "es" ? "Sincronizando..." : "Syncing...";
    }
    try {
      const evs = await getEvents(state.sport);
      state.events = evs;
      renderDateFilter();
      renderCompFilter(state.events);
      renderMatchList();
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
      if (syncTxt) syncTxt.textContent = state.lang === "es" ? "Sincronizado" : "Synced";
    }
  }

  function startPolling() {
    setInterval(() => loadEvents(false), 6000);
    setInterval(() => { if (state.selectedId) refreshDetail(); }, 4000);
    setInterval(refreshBankrollDisplay, 15000);
  }

  // ---------------------------------------------------------------- wiring
  function wireStatic() {
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
        toast(isLight ? (state.lang === "es" ? "Tema claro activado" : "Light theme activated") : (state.lang === "es" ? "Tema oscuro activado" : "Dark theme activated"));
      };
    }

    const refreshBtn = $("#refresh-btn");
    if (refreshBtn) {
      refreshBtn.onclick = async () => {
        refreshBtn.classList.add("spinning");
        const syncTxt = $("#sync-text");
        if (syncTxt) syncTxt.textContent = state.lang === "es" ? "Actualizando..." : "Syncing...";
        try {
          await postJSON("/api/events/refresh", {});
          await loadEvents(true);
          toast(state.lang === "es" ? "Partidos recargados en tiempo real" : "Events reloaded");
        } catch (e) {
          toast(state.lang === "es" ? "Error al conectar con la API" : "Error connecting to API");
        } finally {
          refreshBtn.classList.remove("spinning");
          if (syncTxt) syncTxt.textContent = state.lang === "es" ? "Sincronizado" : "Synced";
        }
      };
    }
    $$(".lang-toggle button").forEach((b) => {
      if (b.dataset.lang === state.lang) b.classList.add("active"); else b.classList.remove("active");
      b.onclick = () => {
        state.lang = b.dataset.lang;
        localStorage.setItem("sq_lang", state.lang);
        $$(".lang-toggle button").forEach((x) => x.classList.toggle("active", x === b));
        applyTranslations();
      };
    });
    $$(".odds-toggle button").forEach((b) => {
      if (b.dataset.fmt === state.oddsFmt) b.classList.add("active"); else b.classList.remove("active");
      b.onclick = () => {
        state.oddsFmt = b.dataset.fmt; localStorage.setItem("sq_odds_fmt", state.oddsFmt);
        $$(".odds-toggle button").forEach((x) => x.classList.toggle("active", x === b));
        renderMatchList();
        if (state.detail) renderGroupsAndInfo(state.detail);
      };
    });
    $("#chat-fab").onclick = () => { $("#chat-panel").classList.toggle("open"); syncPanelPositions(); };
    $("#chat-close").onclick = () => { $("#chat-panel").classList.remove("open"); syncPanelPositions(); };
    $("#chat-send").onclick = () => sendChat($("#chat-input").value);
    $("#chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(e.target.value); });
    $$(".chat-suggestions button").forEach((b) => (b.onclick = () => sendChat(b.dataset.q)));

    $("#slip-fab").onclick = () => { $("#slip-panel").classList.toggle("open"); syncPanelPositions(); };
    $("#slip-clear").onclick = async () => { await postJSON("/api/slip/clear", { session_id: state.sessionId }); await refreshSlip(); };
    $("#slip-place").onclick = async () => {
      const stake = parseFloat($("#slip-stake").value || "0");
      if (!(stake > 0)) return toast(state.lang === "es" ? "Ingresa un monto primero" : "Enter a stake first");
      try {
        await postJSON("/api/bets", { session_id: state.sessionId, stake });
        toast(state.lang === "es" ? "Apuesta simulada realizada" : "Paper bet placed");
        $("#slip-panel").classList.remove("open"); syncPanelPositions();
        await refreshSlip(); await refreshBankrollDisplay();
        if (state.detail) renderGroupsAndInfo(state.detail);
      } catch (e) { toast(state.lang === "es" ? "Error al realizar la apuesta" : "Could not place that bet"); }
    };

    $("#bets-btn").onclick = async () => { $("#bets-modal-bg").style.display = "block"; await renderBetsModal(); };
    $("#bets-close").onclick = () => ($("#bets-modal-bg").style.display = "none");
    $("#bets-modal-bg").onclick = (e) => { if (e.target.id === "bets-modal-bg") $("#bets-modal-bg").style.display = "none"; };

    $("#search-input").addEventListener("input", (e) => {
      const q = e.target.value.trim().toLowerCase();
      if (!q) { renderMatchList(); return; }
      const filtered = state.events.filter((ev) => (ev.home + " " + ev.away + " " + ev.competition).toLowerCase().includes(q));
      const prev = state.events; state.events = filtered; renderMatchList(); state.events = prev;
    });
  }

  function checkProtocol() {
    if (window.location.protocol === "file:") {
      const warn = $("#file-protocol-warning");
      if (warn) warn.style.display = "block";
    }
  }

  async function init() {
    checkProtocol();
    wireStatic();
    applyTranslations();
    try { const s = await api("/api/settings"); state.bankrollBase = s.bankroll; $("#bankroll-amt").textContent = s.bankroll.toFixed(2); } catch (e) {}
    await loadEvents(true);
    await refreshSlip();
    await refreshBankrollDisplay();
    startPolling();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
