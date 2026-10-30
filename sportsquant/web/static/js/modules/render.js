// SportsQuant - DOM Rendering and UI Presentation Layer (ES Modules)

import { state, I18N, $, $$, el, getSports, getTabOrder, toast } from "./state.js?v=2.7";
import { setUserOdds } from "./api.js?v=2.7";

// ---------------------------------------------------------------- Formatting
export function decimalToAmerican(d) {
  if (d == null || !isFinite(d) || d <= 1.0) return "-";
  if (d >= 2.0) {
    const us = Math.round((d - 1.0) * 100);
    return "+" + us;
  } else {
    const us = Math.round(-100.0 / (d - 1.0));
    return us.toString(); // already includes negative sign e.g. -150
  }
}

export function fmtOdds(o) {
  if (o == null || !isFinite(o)) return "-";
  if (state.oddsFmt === "us") {
    return decimalToAmerican(o);
  }
  if (o < 10) return o.toFixed(2);
  if (o < 100) return o.toFixed(1);
  return Math.round(o).toString();
}

export function fmtSel(sel) {
  if (!sel) return "-";
  if (state.oddsFmt === "pct") {
    if (sel.prob != null && isFinite(sel.prob)) {
      return (sel.prob * 100).toFixed(1) + "%";
    } else if (sel.odds != null && isFinite(sel.odds) && sel.odds > 0) {
      return ((1 / sel.odds) * 100).toFixed(1) + "%";
    }
    return "-";
  }
  if (state.oddsFmt === "us") {
    if (sel.odds != null && isFinite(sel.odds) && sel.odds > 1.0) {
      return decimalToAmerican(sel.odds);
    }
    if (sel.prob != null && isFinite(sel.prob) && sel.prob > 0 && sel.prob < 1.0) {
      return decimalToAmerican(1.0 / sel.prob);
    }
    return "-";
  }
  return fmtOdds(sel.odds);
}

export function fmtClock(ev) {
  if (ev.status === "finished") return "FT";
  if (ev.status === "scheduled") {
    const d = new Date(ev.kickoff);
    return (
      d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
      "\n" +
      d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    );
  }

  const c = ev.clock || {};
  const isEs = state.lang === "es";
  const sport = ev.sport || "";

  // 1. Baloncesto (Basketball) & Fútbol Americano (NFL / NCAAF)
  if (sport === "basketball" || sport === "american_football") {
    if (c.is_halftime || c.detail?.toLowerCase().includes("half") || c.phase === "ht") {
      return isEs ? "Medio Tiempo" : "Halftime";
    }
    const qLabel = isEs ? "C" : "Q";
    const p = c.period || 1;
    const timeStr = c.clock || (c.display && c.display.includes(":") ? c.display.split(" ")[1] || c.display : "");
    if (c.is_ot || p > 4) {
      const otNum = p > 4 ? ` ${p - 4}` : "";
      return `OT${otNum}${timeStr ? " " + timeStr : ""}`.trim();
    }
    return `${p}${qLabel}${timeStr ? " " + timeStr : ""}`.trim() || `Q${p}`;
  }

  // 2. Hockey sobre Hielo (NHL)
  if (sport === "hockey") {
    if (c.is_halftime || c.detail?.toLowerCase().includes("intermission")) {
      return isEs ? "Descanso" : "Intermission";
    }
    const p = c.period || 1;
    const timeStr = c.clock || (c.display && c.display.includes(":") ? c.display.split(" ")[1] || c.display : "");
    if (c.is_ot || p > 3) {
      return `OT${timeStr ? " " + timeStr : ""}`.trim();
    }
    return `${p}P${timeStr ? " " + timeStr : ""}`.trim() || `${p}P`;
  }

  // 3. Béisbol (MLB / LVBP / LIDOM)
  if (sport === "baseball" || c.inning) {
    const inn = c.inning || 1;
    const isTop = c.half === "top";
    const arrow = isTop ? "▲" : "▼";
    const ordSuffix = isEs
      ? inn === 1 ? "ra" : inn === 2 ? "da" : inn === 3 ? "ra" : (inn === 7 || inn === 8) ? "va" : "ta"
      : inn === 1 ? "st" : inn === 2 ? "nd" : inn === 3 ? "rd" : "th";
    const halfLabel = isEs ? (isTop ? "Alta" : "Baja") : (isTop ? "Top" : "Bot");
    const outStr = c.outs != null && c.outs > 0 ? ` · ${c.outs} ${isEs ? "out" : "out"}${c.outs === 1 ? "" : "s"}` : "";
    return `${arrow} ${halfLabel} ${inn}${ordSuffix}${outStr}`;
  }

  // 4. Fútbol (Soccer)
  if (sport === "soccer" || c.minute != null) {
    if (c.phase === "ht" || c.detail?.toLowerCase().includes("half") || c.detail === "HT") {
      return isEs ? "Entretiempo (ET)" : "Halftime (HT)";
    }
    if (c.minute != null) {
      const min = Math.round(c.minute);
      const isExtra = min > 90 || c.display?.includes("+");
      return `${min}${isExtra ? "+" : ""}'`;
    }
    if (c.display) return c.display;
  }

  // 5. Motorsport / F1
  if (sport === "motorsport") {
    if (c.lap && c.total_laps) {
      return isEs ? `Vuelta ${c.lap}/${c.total_laps}` : `Lap ${c.lap}/${c.total_laps}`;
    }
    if (c.lap) return isEs ? `Vuelta ${c.lap}` : `Lap ${c.lap}`;
    if (c.display) return c.display;
  }

  // 6. MMA / Boxeo
  if (sport === "mma") {
    const r = c.round || 1;
    const timeStr = c.clock ? ` ${c.clock}` : "";
    return isEs ? `Round ${r}${timeStr}` : `R${r}${timeStr}`;
  }

  // 7. Tenis
  if (sport === "tennis") {
    if (c.set) return isEs ? `Set ${c.set}` : `Set ${c.set}`;
    if (c.display) return c.display;
  }

  // Fallbacks limpios (nunca porcentaje genérico)
  if (c.display && !c.display.includes("%")) return c.display;
  return isEs ? "EN VIVO" : "LIVE";
}

export function isSameDay(d1, d2) {
  return (
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate()
  );
}

export function cleanCompBadge(comp) {
  if (!comp) return "COMPETENCIA";
  if (comp.includes("LVBP")) return "🇻🇪 LVBP";
  if (comp.includes("LIDOM")) return "🇩🇴 LIDOM";
  if (comp.includes("LMP")) return "🇲🇽 LMP";
  if (comp.includes("LBPRC")) return "🇵🇷 LBPRC";
  if (comp.includes("Serie del Caribe")) return "🌴 Serie del Caribe";
  if (comp.includes("World Baseball Classic") || comp.includes("WBC"))
    return "⚾ Clásico Mundial (WBC)";
  if (comp.includes("Major League Baseball") || comp.includes("MLB"))
    return "⚾ MLB";
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

export function fmtScheduleTime(ev) {
  if (ev.status === "live") {
    return `<span class="live-dot"></span> EN VIVO ${fmtClock(ev)}`;
  }
  if (ev.status === "finished") {
    return state.lang === "es" ? "Final" : "Final";
  }
  const d = new Date(ev.kickoff);
  const now = new Date();
  const isToday =
    d.getDate() === now.getDate() &&
    d.getMonth() === now.getMonth() &&
    d.getFullYear() === now.getFullYear();
  const tom = new Date(now);
  tom.setDate(tom.getDate() + 1);
  const isTomorrow =
    d.getDate() === tom.getDate() &&
    d.getMonth() === tom.getMonth() &&
    d.getFullYear() === tom.getFullYear();
  const timeStr = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (isToday) return state.lang === "es" ? `🕒 Hoy ${timeStr}` : `🕒 Today ${timeStr}`;
  if (isTomorrow) return state.lang === "es" ? `🕒 Mañana ${timeStr}` : `🕒 Tomorrow ${timeStr}`;
  const dateStr = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return `📅 ${dateStr} ${timeStr}`;
}

export function fmtVenueText(ev) {
  if (ev.venue && (ev.venue.name || ev.venue.city)) {
    const parts = [];
    if (ev.venue.name) parts.push(ev.venue.name);
    if (ev.venue.city) parts.push(ev.venue.city);
    return parts.join(", ");
  }
  return "Estadio Principal";
}

export function translateGroupName(name) {
  if (state.lang !== "es" || !name) return name;

  // 1UP / 2UP / Paid at N Goal Lead
  const upMatch = name.match(/^1x2 \((\d+)UP\) - Paid at (\d+) Goal Lead$/i);
  if (upMatch) {
    const n = upMatch[1];
    return `Resultado Final (${n}UP) - Pago Anticipado con ${n} gol${parseInt(n) > 1 ? "es" : ""} de ventaja`;
  }

  // Exact matching markets
  if (name === "Moneyline") return "Ganador del Partido (Moneyline)";
  if (name === "Moneyline (incl. OT)") return "Ganador (incl. Prórroga / Extras)";
  if (name === "Match Winner") return "Ganador del Partido";
  if (name === "Fight Winner") return "Ganador de la Pelea";
  if (name === "1x2") return "Resultado Final (1X2)";
  if (name === "Both Teams to Score") return "Ambos Equipos Anotan";
  if (name === "Double Chance") return "Doble Oportunidad";
  if (name === "Draw No Bet") return "Empate Apuesta No Válida (DNB)";
  if (name === "Half Time / Full Time") return "Descanso / Final (HT/FT)";
  if (name === "Half Time Result") return "Resultado 1er Tiempo (Descanso)";
  if (name === "Highest Scoring Half") return "Mitad con Más Goles";
  if (name === "First 5 Innings Result") return "Resultado Primeras 5 Entradas (F5)";
  if (name === "60 Minutes Result") return "Resultado Tiempo Regular (60 Min)";
  if (name === "Set Betting") return "Marcador Exacto de Sets";
  if (name === "First Set Winner") return "Ganador del 1er Set";
  if (name === "Correct Score") return "Marcador Exacto";
  if (name === "Winning Margin") return "Margen de Victoria";
  if (name === "Win to Nil") return "Ganador Sin Recibir Gol";
  if (name === "Exact Total Goals") return "Total Exacto de Goles";
  if (name === "Total Goals Odd / Even") return "Goles Totales Par / Impar";
  if (name === "First Goal") return "Primer Gol";
  if (name === "Next Goal") return "Siguiente Gol";
  if (name === "Same Game Multi") return "Combinada Mismo Partido (SGM)";
  if (name === "Method of Victory") return "Método de Victoria";
  if (name === "Fight Goes the Distance") return "La Pelea Llega a la Decisión (Distancia)";
  if (name === "Race Winner") return "Ganador de la Carrera";
  if (name === "Podium Finish (Top 3)") return "Llegada al Podio (Top 3)";
  if (name === "Top 6 Finish") return "Finaliza en Top 6";
  if (name === "Points Finish (Top 10)") return "Finaliza en Puntos (Top 10)";

  // Prefix & Dynamic Matching
  if (name.startsWith("Total Runs ")) return name.replace("Total Runs ", "Total Carreras (Más/Menos) ");
  if (name.startsWith("Total Goals ")) return name.replace("Total Goals ", "Total Goles (Más/Menos) ");
  if (name.startsWith("Total Points ")) return name.replace("Total Points ", "Total de Puntos (Más/Menos) ");
  if (name.startsWith("Total Sets ")) return name.replace("Total Sets ", "Total de Sets ");
  if (name.startsWith("Total Games ")) return name.replace("Total Games ", "Total de Juegos ");
  if (name.startsWith("Total Rounds ")) return name.replace("Total Rounds ", "Total de Asaltos (Rounds) ");
  if (name.startsWith("Total Cards ")) return name.replace("Total Cards ", "Total de Tarjetas ");
  if (name.startsWith("Total Corners ")) return name.replace("Total Corners ", "Total de Córners ");
  if (name.startsWith("1st Half Total Goals ")) return name.replace("1st Half Total Goals ", "Total Goles 1er Tiempo ");
  if (name.startsWith("2nd Half Total Goals ")) return name.replace("2nd Half Total Goals ", "Total Goles 2do Tiempo ");
  if (name.startsWith("Run Line ")) return name.replace("Run Line ", "Línea de Carreras (Run Line) ");
  if (name.startsWith("Puck Line ")) return name.replace("Puck Line ", "Línea de Puck ");
  if (name.startsWith("Spread ")) return name.replace("Spread ", "Hándicap de Puntos (Spread) ");
  if (name.startsWith("Set Handicap ")) return name.replace("Set Handicap ", "Hándicap de Sets ");
  if (name.startsWith("Asian Handicap ")) return name.replace("Asian Handicap ", "Hándicap Asiático ");
  if (name.startsWith("Asian Total Goals ")) return name.replace("Asian Total Goals ", "Total Asiático de Goles ");
  if (name.startsWith("Goal between minutes ")) return name.replace("Goal between minutes ", "Gol entre los minutos ");

  // Team-specific markets
  if (name.endsWith(" Clean Sheet")) return name.replace(" Clean Sheet", " Portería a Cero");
  if (name.includes(" Total Goals ")) return name.replace(" Total Goals ", " Total Goles ");
  if (name.includes(" Total Points ")) return name.replace(" Total Points ", " Total Puntos ");
  if (name.includes(" Cards ")) return name.replace(" Cards ", " Tarjetas ");
  if (name.includes(" Corners ")) return name.replace(" Corners ", " Córners ");
  if (name.includes(" Total ")) return name.replace(" Total ", " Total ");

  return name;
}

export function translateNote(note) {
  if (state.lang !== "es" || !note) return note;

  // Lead hit / UP note
  if (note.includes("pay out as a win as soon as that team leads by")) {
    return note.replace(
      /Home \/ Away pay out as a win as soon as that team leads by (\d+)\.?/i,
      "Ganas automáticamente la apuesta tan pronto como el equipo tome $1 gol(es) de ventaja."
    );
  }
  if (note === "Stake is returned if the match ends level.") {
    return "La apuesta se reembolsa en su totalidad en caso de empate.";
  }
  if (note.includes("Push-adjusted probability; quarter lines split the stake.")) {
    return "Probabilidad ajustada; las líneas asiáticas dividen la apuesta (medio gane / medio reembolso).";
  }
  if (note === "Approximation: the two halves are treated as independent.") {
    return "Aproximación cuantitativa: ambas mitades se modelan de forma matemáticamente independiente.";
  }
  if (note.includes("Joint probabilities computed exactly on the scoreline table")) {
    return "Probabilidades calculadas con la matriz conjunta de marcadores (las selecciones están correlacionadas).";
  }
  if (note.includes("Pre-match approximation (rates scaled to 5 innings).")) {
    return "Aproximación prematch (tasas proyectadas a las primeras 5 entradas).";
  }
  if (note === "Each driver is an independent yes/no bet.") {
    return "Cada piloto se evalúa como una selección independiente Sí/No.";
  }
  if (note.startsWith("Referee:")) {
    return note
      .replace(/^Referee:/, "Árbitro:")
      .replace(/vs an average referee/, "vs la media de árbitros");
  }
  return note;
}

export function translateLabel(lbl) {
  if (state.lang !== "es" || !lbl) return lbl;
  if (lbl === "Draw" || lbl === "Tie") return "Empate";
  if (lbl === "Over") return "Más de";
  if (lbl === "Under") return "Menos de";
  if (lbl === "Yes") return "Sí";
  if (lbl === "No") return "No";
  if (lbl === "Odd") return "Impar";
  if (lbl === "Even") return "Par";
  if (lbl === "Any other score") return "Cualquier otro marcador";
  if (lbl === "No goal") return "Sin goles";
  if (lbl === "1st half") return "1ª Mitad";
  if (lbl === "2nd half") return "2ª Mitad";
  if (lbl === "Equal") return "Mismo número";

  let res = lbl;
  if (res.startsWith("Over ")) res = res.replace("Over ", "Más de ");
  if (res.startsWith("Under ")) res = res.replace("Under ", "Menos de ");
  if (res.includes(" or Draw")) res = res.replace(" or Draw", " o Empate");
  if (res.startsWith("Draw or ")) res = res.replace("Draw or ", "Empate o ");

  // SGM (Same Game Multi) patterns
  res = res.replace(/\bto win & Over\b/g, "gana y Más de");
  res = res.replace(/\bto win & Under\b/g, "gana y Menos de");
  res = res.replace(/\bto win & Both teams score\b/g, "gana y Ambos anotan");
  res = res.replace(/^Draw & Under\b/g, "Empate y Menos de");
  res = res.replace(/^Draw & Both teams score\b/g, "Empate y Ambos anotan");
  res = res.replace(/^Both teams score & Over\b/g, "Ambos anotan y Más de");
  res = res.replace(/^Both teams score & Under\b/g, "Ambos anotan y Menos de");
  res = res.replace(/^Both teams NOT score & Under\b/g, "Ambos NO anotan y Menos de");
  res = res.replace(/\bor Draw & Under\b/g, "o Empate y Menos de");
  res = res.replace(/\bor Draw & Over\b/g, "o Empate y Más de");

  // Combat methods & margins
  res = res.replace(/\bby KO\/TKO\b/g, "por KO/TKO");
  res = res.replace(/\bby Submission\b/g, "por Sumisión");
  res = res.replace(/\bby Decision\b/g, "por Decisión");
  res = res.replace(/\bby 3\+\b/g, "por 3+");
  res = res.replace(/\bby 2\b/g, "por 2");
  res = res.replace(/\bby 1\b/g, "por 1");

  return res;
}

export function groupKindClass(g) {
  const n = g.selections.length;
  if (g.kind === "3way") return "k-3";
  if (g.kind === "2way") return "k-2";
  return n <= 4 ? "k-2" : "k-multi";
}

// ---------------------------------------------------------------- Loading Indicators
export function showLoadingBar() {
  const b = $("#top-progress-bar");
  if (b) b.classList.add("active");
}

export function hideLoadingBar() {
  const b = $("#top-progress-bar");
  if (b) b.classList.remove("active");
}

export function renderListLoading() {
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

export function renderDetailLoading(title) {
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

// ---------------------------------------------------------------- Mobile Helpers
export function showListMobile() {
  $("#col-list")?.classList.remove("hidden-mobile");
  $("#col-detail")?.classList.add("hidden-mobile");
}

export function showDetailMobile() {
  $("#col-list")?.classList.add("hidden-mobile");
  $("#col-detail")?.classList.remove("hidden-mobile");
}

// ---------------------------------------------------------------- Callback References (Persistent)
let currentOnSelectSport = null;
let currentOnSelectDate = null;
let currentOnRefreshAPI = null;
let currentOnSelectComp = null;
let currentOnSelectMatch = null;

// ---------------------------------------------------------------- Rail
export function renderRail(onSelectSport) {
  if (onSelectSport !== undefined) currentOnSelectSport = onSelectSport;
  const rail = $("#rail");
  if (!rail) return;
  rail.innerHTML = "";
  getSports().forEach((s) => {
    const b = el(
      "button",
      "rail-item" + (s.id === state.sport ? " active" : ""),
      `<span class="ic">${s.ic}</span><span>${s.label}</span>`
    );
    b.onclick = () => {
      $$(".rail-item").forEach((item) => item.classList.remove("active"));
      b.classList.add("active");
      if (currentOnSelectSport) currentOnSelectSport(s.id);
    };
    rail.appendChild(b);
  });
}

// ---------------------------------------------------------------- Filters & Match List
export function competitionsOf(events) {
  const seen = new Map();
  events.forEach((e) => seen.set(e.competition, (seen.get(e.competition) || 0) + 1));
  return Array.from(seen.entries()).sort((a, b) => b[1] - a[1]);
}

export function renderDateFilter(onSelectDate, onRefreshAPI) {
  if (onSelectDate !== undefined) currentOnSelectDate = onSelectDate;
  if (onRefreshAPI !== undefined) currentOnRefreshAPI = onRefreshAPI;
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
    const btn = el(
      "button",
      "chip" + (state.dateFilter === opt.id ? " active" : ""),
      opt.label
    );
    btn.onclick = () => {
      state.dateFilter = opt.id;
      if (currentOnSelectDate) currentOnSelectDate(opt.id);
    };
    box.appendChild(btn);
  });
  const refBtn = el("button", "chip chip-refresh", t.recargar_api_chip);
  refBtn.onclick = async () => {
    if (currentOnRefreshAPI) await currentOnRefreshAPI(refBtn);
  };
  box.appendChild(refBtn);
}

export function renderCompFilter(events, onSelectComp) {
  if (onSelectComp !== undefined) currentOnSelectComp = onSelectComp;
  const box = $("#comp-filter");
  if (!box) return;
  box.innerHTML = "";
  const all = el(
    "button",
    "chip" + (state.compFilter === null ? " active" : ""),
    state.lang === "es" ? "Todas" : "All"
  );
  all.onclick = () => {
    state.compFilter = null;
    if (currentOnSelectComp) currentOnSelectComp(null);
  };
  box.appendChild(all);
  competitionsOf(events).forEach(([name, n]) => {
    const c = el(
      "button",
      "chip" + (state.compFilter === name ? " active" : ""),
      `${name} (${n})`
    );
    c.onclick = () => {
      state.compFilter = name;
      if (currentOnSelectComp) currentOnSelectComp(name);
    };
    box.appendChild(c);
  });
}

export function renderMatchList(onSelectMatch) {
  if (onSelectMatch !== undefined) currentOnSelectMatch = onSelectMatch;
  const list = $("#match-list");
  if (!list) return;
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

  list.innerHTML = "";
  evs.forEach((e) => {
    const row = el(
      "div",
      "match-row" + (e.id === state.selectedId ? " selected" : "")
    );
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

    row.onclick = () => {
      if (currentOnSelectMatch) currentOnSelectMatch(e.id);
    };
    list.appendChild(row);
  });
}

// ---------------------------------------------------------------- Detail View
export function renderTabs(groups, onTabSelect) {
  const present = new Set(groups.map((g) => g.tab));
  const bar = $("#market-tabs");
  if (!bar) return;
  bar.innerHTML = "";
  const order = getTabOrder().filter(([id]) => present.has(id));
  if (!order.some(([id]) => id === state.activeTab)) {
    state.activeTab = order.length ? order[0][0] : "main";
  }
  order.forEach(([id, label]) => {
    const b = el("button", "mtab" + (id === state.activeTab ? " active" : ""), label);
    b.onclick = () => {
      state.activeTab = id;
      if (onTabSelect) onTabSelect(id);
    };
    bar.appendChild(b);
  });
}

export function renderHeader(d) {
  const t = I18N[state.lang];
  const ev = d.event;
  const box = $("#detail-header");
  if (!box) return;
  const conf = d.info.confidence || "ok";
  const confCls = conf === "ok" ? "conf-ok" : conf === "demo" ? "conf-demo" : "conf-low";
  const badgeText = conf === "demo" ? t.demo_model : conf === "ok" ? t.fitted_model : t.low_confidence;
  const backBtnText = state.lang === "es" ? "‹ Partidos" : "‹ Matches";
  let statusClock = "";
  if (ev.status === "live") {
    statusClock = "● " + (state.lang === "es" ? "EN VIVO" : "LIVE") + " - " + fmtClock(ev);
  } else if (ev.status === "finished") {
    statusClock = state.lang === "es" ? "Tiempo Completo (FT)" : "Full time (FT)";
  } else {
    const d = new Date(ev.kickoff);
    const timeStr = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    const dateStr = d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
    const tzShort = new Date().toLocaleTimeString([], { timeZoneName: "short" }).split(" ")[2] || "";
    const tzLabel = tzShort ? `(${tzShort})` : "";
    statusClock = (state.lang === "es" ? "Inicio: " : "Kickoff: ") + `${dateStr} · ${timeStr} ${tzLabel}`.trim();
  }

  box.innerHTML = `
    <div class="dh-top"><button class="back-btn" id="back-btn">${backBtnText}</button><span>${ev.competition}</span></div>
    <div class="dh-teams">
      <div class="dh-team home">${ev.home}</div>
      <div class="dh-score">${ev.status === "scheduled" ? "vs" : ev.score[0] + " - " + ev.score[1]}</div>
      <div class="dh-team away">${ev.away}</div>
    </div>
    <div class="dh-clock ${ev.status}">${statusClock}</div>
    <div class="dh-meta">
      <span class="confidence-badge ${confCls}">${badgeText}</span>
      ${d.referee ? `<span>🧑‍⚖️ ${d.referee}</span>` : ""}
      ${d.venue && d.venue.name ? `<span>📍 ${d.venue.name}</span>` : ""}
    </div>`;
  const backBtn = $("#back-btn");
  if (backBtn) backBtn.onclick = showListMobile;
}

export function renderInfoCol(d) {
  const t = I18N[state.lang];
  const box = $("#info-col");
  if (!box) return;
  box.innerHTML = "";
  const model = el("div", "info-card");
  model.innerHTML = `<h4>${t.model_title}</h4>
    <div class="info-row"><span class="k">${t.method}</span><span class="v" style="text-align:right;max-width:60%">${d.info.model || "-"}</span></div>
    ${d.info.expected_final ? `<div class="info-row"><span class="k">${t.exp_score}</span><span class="v num">${d.info.expected_final[0].toFixed(2)} - ${d.info.expected_final[1].toFixed(2)}</span></div>` : ""}
    ${d.info.expected_margin != null ? `<div class="info-row"><span class="k">${t.exp_margin}</span><span class="v num">${d.info.expected_margin.toFixed(1)}</span></div>` : ""}
    ${d.info.expected_total != null ? `<div class="info-row"><span class="k">${t.exp_total}</span><span class="v num">${d.info.expected_total.toFixed(1)}</span></div>` : ""}
    <div class="info-row"><span class="k">${t.odds_fmt_label}</span><span class="v">${
      state.oddsFmt === "pct"
        ? (state.lang === "es" ? "% Probabilidad" : "% Probability")
        : state.oddsFmt === "us"
        ? (state.lang === "es" ? "Momio Americano (±100)" : "American Odds (±100)")
        : (state.lang === "es" ? "Cuota Decimal" : "Decimal Odds")
    }</span></div>`;
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

export function flashChanges(groups) {
  const flat = {};
  groups.forEach((g) =>
    g.selections.forEach((s) => {
      flat[g.id + ":" + s.id] = s.odds;
    })
  );
  Object.keys(flat).forEach((k) => {
    const prev = state.prevFlat[k];
    if (prev != null && Math.abs(prev - flat[k]) > 1e-6) {
      const btn = document.querySelector(`.sel-btn[data-flat-key="${CSS.escape(k)}"]`);
      if (btn) {
        btn.classList.remove("flash-up", "flash-down");
        void btn.offsetWidth;
        btn.classList.add(flat[k] > prev ? "flash-up" : "flash-down");
      }
    }
  });
  state.prevFlat = flat;
}

export async function promptEditUserOdds(g, s, onSaved) {
  const cur = s.user_odds != null ? s.user_odds : "";
  const promptMsg =
    state.lang === "es"
      ? `Cuota de tu casa de apuestas para "${s.label}" (${g.name}) - cuota decimal, blanco para borrar:`
      : `Your sportsbook price for "${s.label}" (${g.name}) - decimal odds, blank to clear:`;
  const val = prompt(promptMsg, cur);
  if (val === null) return;
  const num = val.trim() === "" ? null : parseFloat(val);
  try {
    await setUserOdds(state.selectedId, g.id + ":" + s.id, num);
    toast(
      num == null
        ? state.lang === "es" ? "Cuota borrada" : "Cleared price"
        : state.lang === "es" ? "Cuota guardada - buscando valor" : "Saved price"
    );
    if (onSaved) await onSaved();
  } catch (e) {
    toast(state.lang === "es" ? "Error al guardar la cuota" : "Could not save that price");
  }
}

export function renderGroup(g, isPickedFn, onToggleSlip, onDetailRefresh) {
  const card = el("div", "group-card");
  const head = el("div", "group-head");
  head.innerHTML =
    `<span class="name">${translateGroupName(g.name)}</span>` +
    (g.note ? `<span class="note">${translateNote(g.note)}</span>` : "");
  card.appendChild(head);
  const sels = el("div", "group-sels " + groupKindClass(g));
  g.selections.forEach((s) => {
    const picked = isPickedFn ? isPickedFn(g.id, s.id) : false;
    const btn = el("button", "sel-btn" + (picked ? " picked" : ""));
    btn.innerHTML = `<span class="sel-label">${translateLabel(s.label)}</span><span class="sel-odds num">${fmtSel(s)}</span>`;
    btn.dataset.flatKey = g.id + ":" + s.id;
    btn.onclick = () => {
      if (onToggleSlip) onToggleSlip(g, s, btn);
    };
    btn.oncontextmenu = (ev) => {
      ev.preventDefault();
      promptEditUserOdds(g, s, onDetailRefresh);
    };
    sels.appendChild(btn);
  });
  card.appendChild(sels);
  return card;
}

export function renderGroupsAndInfo(d, isPickedFn, onToggleSlip, onDetailRefresh) {
  renderTabs(d.groups, () => renderGroupsAndInfo(d, isPickedFn, onToggleSlip, onDetailRefresh));
  const col = $("#groups-col");
  if (!col) return;
  col.innerHTML = "";
  d.groups
    .filter((g) => g.tab === state.activeTab)
    .forEach((g) => col.appendChild(renderGroup(g, isPickedFn, onToggleSlip, onDetailRefresh)));
  renderInfoCol(d);
  flashChanges(d.groups);
}

export function renderDetail(d, isPickedFn, onToggleSlip, onDetailRefresh) {
  state.detail = d;
  const empty = $("#empty-detail");
  if (empty) empty.style.display = "none";
  let wrap = $("#detail-wrap");
  if (!wrap) {
    const cd = $("#col-detail");
    if (cd) {
      cd.innerHTML = "";
      wrap = el("div", "", "");
      wrap.id = "detail-wrap";
      wrap.style.display = "contents";
      cd.innerHTML = `
        <div id="detail-header"></div>
        <div id="market-tabs"></div>
        <div id="market-body">
          <div id="groups-col"></div>
          <div id="info-col"></div>
        </div>
      `;
    }
  }
  renderHeader(d);
  renderGroupsAndInfo(d, isPickedFn, onToggleSlip, onDetailRefresh);
}

export function clearDetail() {
  state.selectedId = null;
  state.detail = null;
  const t = I18N[state.lang];
  const cd = $("#col-detail");
  if (cd) {
    cd.innerHTML = `<div id="empty-detail" class="empty-state">${t.empty_detail}</div>`;
  }
}

export function renderBetsModal(bets, onDeleteBet, onClearAllBets) {
  const box = $("#bets-list");
  const countBadge = $("#bets-count-badge");
  const clearAllBtn = $("#bets-clear-all");
  if (countBadge) countBadge.textContent = bets ? bets.length : 0;
  if (clearAllBtn) {
    clearAllBtn.style.display = bets && bets.length > 0 ? "inline-flex" : "none";
    if (onClearAllBets) {
      clearAllBtn.onclick = onClearAllBets;
    }
  }
  if (!box) return;
  if (!bets || !bets.length) {
    box.innerHTML = `<p style='color:var(--text-faint);text-align:center;padding:24px 0;'>${state.lang === "es" ? "Sin apuestas simuladas aún." : "No paper bets yet."}</p>`;
    return;
  }
  const frag = document.createDocumentFragment();
  bets.forEach((b) => {
    const row = el("div", "slip-leg");
    const statusColor =
      b.status === "won" ? "var(--teal)" : b.status === "lost" ? "var(--coral)" : "var(--text-dim)";
    const statusLabel =
      b.status === "won" ? (state.lang === "es" ? "GANADA" : "WON")
      : b.status === "lost" ? (state.lang === "es" ? "PERDIDA" : "LOST")
      : (state.lang === "es" ? "ABIERTA" : "OPEN");
    row.innerHTML = `
      <div class="top">
        <span class="sel">${state.lang === "es" ? "Monto" : "Stake"} $${b.stake.toFixed(2)} - <span style="color:${statusColor}">${statusLabel}</span></span>
        <div style="display:flex;align-items:center;">
          <span class="num" style="color:${b.pnl > 0 ? "var(--teal)" : b.pnl < 0 ? "var(--coral)" : "var(--text-dim)"}">
            ${b.pnl > 0 ? "+" : ""}${b.pnl.toFixed(2)}
          </span>
          <button class="bet-del-btn" title="${state.lang === "es" ? "Eliminar esta apuesta" : "Delete this bet"}">🗑</button>
        </div>
      </div>
      <div class="ev">${b.legs.map((l) => l.label || l.key).join(" · ")}</div>
    `;
    const delBtn = row.querySelector(".bet-del-btn");
    if (delBtn && onDeleteBet) {
      delBtn.onclick = (e) => {
        e.stopPropagation();
        onDeleteBet(b.id);
      };
    }
    frag.appendChild(row);
  });
  box.innerHTML = "";
  box.appendChild(frag);
}

// ---------------------------------------------------------------- Global Translation Applier
export function applyTranslations(isPickedFn, onToggleSlip, onDetailRefresh) {
  const t = I18N[state.lang];
  const tagPaper = $("#tag-paper");
  if (tagPaper) tagPaper.textContent = "Parley Project by JS-JT-EB 2026";
  const searchInput = $("#search-input");
  if (searchInput) searchInput.placeholder = t.search_placeholder;
  const txtReload = $("#txt-reload");
  if (txtReload) txtReload.textContent = t.reload_api;
  const lblBankroll = $("#lbl-bankroll");
  if (lblBankroll) lblBankroll.textContent = t.paper_bankroll;
  const emptyDetail = $("#empty-detail");
  if (emptyDetail) {
    emptyDetail.innerHTML =
      state.lang === "es"
        ? "Selecciona un partido a la izquierda para ver predicciones cuantitativas y cuotas justas en tiempo real.<br><small style='color:var(--text-dim)'>Simulación deportiva analítica · Sin dinero real · Solo fines de estudio</small>"
        : "Pick a match on the left to see live quantitative predictions and fair markets.<br><small style='color:var(--text-dim)'>Paper trading simulation · Not real money · Not betting advice</small>";
  }
  const betsModalTitle = $("#bets-modal-title") || $("#bets-modal-bg strong");
  if (betsModalTitle) {
    betsModalTitle.textContent = state.lang === "es" ? "Mis apuestas simuladas" : "My paper bets";
  }

  const slipTitle = $("#slip-title");
  if (slipTitle) slipTitle.textContent = t.bet_slip;
  const slipClear = $("#slip-clear");
  if (slipClear) slipClear.textContent = t.clear;
  const slipClose = $("#slip-close");
  if (slipClose) slipClose.title = t.close_slip;
  const slipFabText = $("#slip-fab-text");
  if (slipFabText) slipFabText.textContent = t.bet_slip;
  const lblTrueProb = $("#lbl-true-prob");
  if (lblTrueProb) lblTrueProb.textContent = t.true_prob;
  const lblFairOdds = $("#lbl-fair-odds");
  if (lblFairOdds) lblFairOdds.textContent = t.fair_odds;
  const lblNetProfit = $("#lbl-net-profit");
  if (lblNetProfit) lblNetProfit.textContent = t.net_profit;
  const lblTotalPayout = $("#lbl-total-payout");
  if (lblTotalPayout) lblTotalPayout.textContent = t.total_payout;
  const betsClearAll = $("#bets-clear-all");
  if (betsClearAll) betsClearAll.textContent = t.clear_history;
  const slipStake = $("#slip-stake");
  if (slipStake) slipStake.placeholder = t.paper_stake;
  const slipPlace = $("#slip-place");
  if (slipPlace) slipPlace.textContent = t.place_bet;

  const chatHead = $("#chat-panel .chat-head .title");
  if (chatHead) chatHead.innerHTML = `<span class="dot"></span> ${t.assistant_title}`;
  const chatInput = $("#chat-input");
  if (chatInput) chatInput.placeholder = t.ask_placeholder;
  const sugBtns = $$(".chat-suggestions button");
  if (sugBtns[0]) {
    sugBtns[0].textContent = state.lang === "es" ? "🏆 Mejores logros" : "🏆 Best +EV bets";
    sugBtns[0].dataset.q =
      state.lang === "es"
        ? "mejores logros de hoy"
        : "best value bets today";
  }
  if (sugBtns[1]) {
    sugBtns[1].textContent = state.lang === "es" ? "📈 Consenso Covers" : "📈 Covers consensus";
    sugBtns[1].dataset.q =
      state.lang === "es"
        ? "consenso covers"
        : "covers consensus";
  }
  if (sugBtns[2]) {
    sugBtns[2].textContent = state.lang === "es" ? "💰 ¿Qué más paga?" : "💰 Highest payouts";
    sugBtns[2].dataset.q = state.lang === "es" ? "que es lo que mas paga" : "highest payouts";
  }
  if (sugBtns[3]) {
    sugBtns[3].textContent = state.lang === "es" ? "🎲 Analizar mi boleta" : "🎲 Price my slip";
    sugBtns[3].dataset.q = state.lang === "es" ? "analizar mi boleta" : "price my slip";
  }

  renderRail();
  renderDateFilter();
  renderCompFilter(state.events);
  renderMatchList();
  if (state.detail) {
    renderHeader(state.detail);
    renderInfoCol(state.detail);
    renderGroupsAndInfo(state.detail, isPickedFn, onToggleSlip, onDetailRefresh);
  }
}
