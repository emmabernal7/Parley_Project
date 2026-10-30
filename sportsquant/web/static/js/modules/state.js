// SportsQuant - Shared State, Selectors and Internationalization (ES Modules)

export const I18N = {
  es: {
    paper_trading: "Parley Project by JS-JT-EB 2026",
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
    bet_slip: "Boleta de Apuesta Simulada",
    clear: "Vaciar",
    true_prob: "Probabilidad justa",
    fair_odds: "Cuotas estimadas",
    net_profit: "Ganancia neta",
    total_payout: "Retorno total",
    clear_history: "🗑 Vaciar historial",
    clear_history_confirm: "¿Estás seguro de que deseas vaciar todo el historial de apuestas?",
    history_cleared: "Historial de apuestas vaciado con éxito",
    close_slip: "Cerrar",
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
      motorsport: "F1"
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
    paper_trading: "Parley Project by JS-JT-EB 2026",
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
    bet_slip: "Boleta de Apuesta Simulada",
    clear: "Clear",
    true_prob: "True probability",
    fair_odds: "Fair odds",
    net_profit: "Net profit",
    total_payout: "Total payout",
    clear_history: "🗑 Clear history",
    clear_history_confirm: "Are you sure you want to clear all paper bet history?",
    history_cleared: "Bet history cleared successfully",
    close_slip: "Close",
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
      motorsport: "F1"
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

export const $ = (sel, el) => (el || document).querySelector(sel);
export const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
export const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};

export function uid() {
  return "s_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

let toastTimer = null;
export function toast(msg) {
  const t = $("#toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

export const state = {
  sessionId: localStorage.getItem("sq_session") || (() => {
    const v = uid();
    localStorage.setItem("sq_session", v);
    return v;
  })(),
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

export function getSports() {
  const t = I18N[state.lang]?.sports || I18N.es.sports;
  return [
    { id: "soccer", ic: "⚽", label: t.soccer },
    { id: "basketball", ic: "🏀", label: t.basketball },
    { id: "american_football", ic: "🏈", label: t.american_football },
    { id: "baseball", ic: "⚾", label: t.baseball },
    { id: "hockey", ic: "🏒", label: t.hockey },
    { id: "tennis", ic: "🎾", label: t.tennis },
    { id: "volleyball", ic: "🏐", label: t.volleyball },
    { id: "mma", ic: "🥊", label: t.mma },
    { id: "motorsport", ic: "🏎️", label: t.motorsport }
  ];
}

export function getTabOrder() {
  const t = I18N[state.lang]?.tabs || I18N.es.tabs;
  return [
    ["main", t.main],
    ["sgm", t.sgm],
    ["goals", t.goals],
    ["asian", t.asian],
    ["half", t.half],
    ["lines", t.lines],
    ["specials", t.specials],
    ["minute", t.minute],
  ];
}
