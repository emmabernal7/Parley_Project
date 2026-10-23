"""Conversational layer.  Every number in a reply comes from ToolBox (real math on real model
output) - the offline router calls those functions directly from parsed intent; the online
(Anthropic / Gemini) path lets an LLM call the same functions as tools.  Both end up stating only
numbers the ToolBox actually computed.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Tuple

import requests

from ..odds import fmt_odds, fmt_pct
from ..settings import get_settings
from .tools import TOOL_SPECS, ToolBox

log = logging.getLogger(__name__)

DISCLAIMER = ("Model probabilities are estimates, not guarantees - the market is often right, and the house "
             "edge means most bettors lose over time. This is a research tool, not financial advice; bet only "
             "what you can afford to lose, and treat it as a paper-trading exercise until it has proven "
             "itself against closing lines over a real sample of bets.")

SYSTEM_PROMPT = (
    "You are the expert quantitative sports-analytics and betting assistant for SportsQuant. "
    "Respond in the same language used by the user (Spanish or English). "
    "Always call tools to retrieve model probabilities, odds, and value metrics - never guess numbers. "
    "When asked about specific bets (e.g. 'Over 3.5 runs by Tampa Bay vs Guardians', 'Over 2.5 goals in Real Madrid vs Barcelona'), call analyze_proposition to obtain the exact mathematical probability, fair odds, and pitching/tactical metrics. "
    "When asked for an opinion, analysis, feedback, or review of a match or bet slip, provide a structured breakdown including: "
    "1. Model Opinion & Fair Odds (Probabilidad y Cuota Justa)\n"
    "2. Value & Edge Analysis (+EV / Valor Esperado)\n"
    "3. Risk Level & Volatility (Bajo, Moderado, Elevado)\n"
    "4. Bankroll Sizing Recommendation (Fractional Kelly %)\n"
    "Keep your tone professional, analytical, objective, and encouraging. Never tell the user they MUST bet real money."
)


# ============================================================================ offline router
MARKET_WORDS = {
    "win": ("1x2", None), "moneyline": ("1x2", None), "1x2": ("1x2", None), "money line": ("1x2", None),
    "both teams to score": ("btts", "yes"), "btts": ("btts", "yes"),
    "clean sheet": ("cs_home", "yes"), "double chance": ("dc", None), "draw no bet": ("dnb", None),
}


class OfflineChat:
    """Keyword / pattern router.  No external calls; always available."""

    def __init__(self, tools: ToolBox):
        self.tools = tools

    def reply(self, message: str, session: Dict) -> str:
        text = message.strip()
        low = text.lower()

        # Greetings
        if re.search(r"\b(hi|hello|hey|hola|buenas|buen(os)?\s*(dias|tardes|noches))\b", low) and len(low) < 25:
            return ("¡Hola! Soy tu asistente de análisis cuantitativo deportivo. "
                    "Puedes preguntarme sobre cualquier equipo o partido (\"Opinión de Barcelona\"), "
                    "hacerme consultas específicas sobre apuestas (\"Over 3.5 runs de Tampa Bay vs Guardians\"), "
                    "buscar \"apuestas de valor\", analizar tu boleto (\"analizar mi boleto\") o calcular la gestión de banca Kelly.")

        # Specific team total / line proposition (e.g. Over 3.5 runs by Tampa Bay vs Guardians)
        prop_res = self._check_proposition(text, low)
        if prop_res:
            return prop_res

        # Value / +EV
        if re.search(r"\bvalue\b|\+ev\b|best bets?\b|apuestas? de valor\b|mejores apuestas\b|valor\b", low):
            return self._value(low)

        # Slip / Parlay / Combinada
        if re.search(r"\bslip\b|\bparlay\b|\bcombo\b|\bmulti\b|\bboleto\b|\bcombinada\b", low) or "price" in low or "analiz" in low and ("boleto" in low or "slip" in low or "parlay" in low):
            return self._slip(session)

        # Kelly / Stake / Banca
        if re.search(r"\bkelly\b|\bstake\b|\bbankroll\b|\bgestion\b|\bbanca\b", low):
            m = self._parse_stake(low)
            if m:
                prob, odds = m
                r = self.tools.bankroll_stake(prob, odds)
                return (f"📊 **Análisis de Banca (Criterio de Kelly):**\n\n"
                        f"• Probabilidad estimada: **{fmt_pct(prob)}** | Cuota: **{fmt_odds(odds)}**\n"
                        f"• Ventaja matemática (Edge): **+{r['edge_pct']}%**\n"
                        f"• Stake Sugerido (Fractional Kelly 25%): **{r['kelly_fraction_pct']}%** de tu banca "
                        f"(~**${r['suggested_stake']:.2f}** para una banca de ${r['bankroll']:.0f}).\n\n"
                        f"💡 *Recomendación:* Mantén siempre disciplina de banca para mitigar la varianza.")
            return "Indícame la probabilidad y la cuota, por ejemplo: \"kelly stake para 55% a 2.10\"."

        # Referee
        if re.search(r"\breferee\b|\bref\b|\barbitro\b|\bárbitro\b", low):
            return self._referee(low)

        # Devig
        if re.search(r"\bdevig\b|remove (the )?margin|overround|quitar margen|margen", low):
            nums = [float(x) for x in re.findall(r"\d+\.\d+|\d+", low)]
            if len(nums) >= 2:
                r = self.tools.devig_prices(nums)
                pairs = ", ".join(f"{fmt_odds(o)}" for o in r["fair_odds"])
                return f"Overround de la casa: **{r['overround_pct']}%**.\nCuotas justas sin margen: **{pairs}**."
            return "Indícame las cuotas para eliminar el margen, ej: \"devig 1.9 3.6 4.2\"."

        # Match lookup / Opinion & Feedback
        return self._match_lookup_and_opinion(text, low)

    # -------------------------------------------------------------- helpers
    def _check_proposition(self, text: str, low: str) -> Optional[str]:
        dir_m = re.search(r"\b(over|under|más de|mas de|menos de)\b", low)
        num_m = re.search(r"(\d+(?:\.\d+)?)", low)
        stat_m = re.search(r"\b(runs?|carreras?|goals?|goles?|points?|puntos?|sets?|rounds?|tarjetas?|corners?)\b", low)

        if dir_m and num_m:
            direction = "over" if ("over" in dir_m.group(1) or "más" in dir_m.group(1) or "mas" in dir_m.group(1)) else "under"
            line = float(num_m.group(1))
            stat_type = stat_m.group(1) if stat_m else "runs"

            cleaned = re.sub(r"\b(what|does|it|think|about|an|the|by|for|of|in|today|hoy|que|opinas|sobre|de|del|un|una|tendra|anotara|marcara|over|under|más de|mas de|menos de|runs?|carreras?|goals?|goles?|points?|puntos?)\b", " ", low)
            cleaned = re.sub(r"\d+(?:\.\d+)?", " ", cleaned).strip()

            parts = re.split(r"\b(?:vs|contra|against)\b", cleaned)
            team = parts[0].strip()
            opponent = parts[1].strip() if len(parts) > 1 else None

            # Common team nickname aliases
            alias_map = {
                "tampa": "Tampa Bay Rays", "tampa bay": "Tampa Bay Rays", "rays": "Tampa Bay Rays",
                "guardians": "Cleveland Guardians", "cleveland": "Cleveland Guardians",
                "yankees": "New York Yankees", "dodgers": "Los Angeles Dodgers",
                "red sox": "Boston Red Sox", "astros": "Houston Astros",
                "celtics": "Boston Celtics", "lakers": "Los Angeles Lakers",
                "warriors": "Golden State Warriors", "nuggets": "Denver Nuggets",
                "chiefs": "Kansas City Chiefs", "niners": "San Francisco 49ers", "49ers": "San Francisco 49ers",
                "ravens": "Baltimore Ravens", "bills": "Buffalo Bills",
                "oilers": "Edmonton Oilers", "panthers": "Florida Panthers",
                "rangers": "New York Rangers", "maple leafs": "Toronto Maple Leafs",
                "barca": "Barcelona", "barcelona": "Barcelona",
                "madrid": "Real Madrid", "real madrid": "Real Madrid",
                "city": "Manchester City", "manchester city": "Manchester City",
                "brentford": "Brentford", "bayern": "Bayern Munich",
                "inter": "Inter Milan", "boca": "Boca Juniors", "river": "River Plate",
                # Caribbean Baseball (LVBP, LIDOM, LMP, LBPRC)
                "caracas": "Leones del Caracas", "leones del caracas": "Leones del Caracas",
                "magallanes": "Navegantes del Magallanes", "navegantes": "Navegantes del Magallanes",
                "la guaira": "Tiburones de La Guaira", "tiburones": "Tiburones de La Guaira",
                "cardenales": "Cardenales de Lara", "lara": "Cardenales de Lara",
                "aragua": "Tigres de Aragua", "tigres de aragua": "Tigres de Aragua",
                "zulia": "Águilas del Zulia", "aguilas del zulia": "Águilas del Zulia",
                "caribes": "Caribes de Anzoátegui", "anzoategui": "Caribes de Anzoátegui",
                "margarita": "Bravos de Margarita", "bravos": "Bravos de Margarita",
                "licey": "Tigres del Licey", "tigres del licey": "Tigres del Licey",
                "escogido": "Leones del Escogido", "leones del escogido": "Leones del Escogido",
                "aguilas cibaeñas": "Águilas Cibaeñas", "aguilas cibaenas": "Águilas Cibaeñas",
                "gigantes del cibao": "Gigantes del Cibao", "toros del este": "Toros del Este",
                "estrellas orientales": "Estrellas Orientales",
                "hermosillo": "Naranjeros de Hermosillo", "naranjeros": "Naranjeros de Hermosillo",
                "culiacan": "Tomateros de Culiacán", "tomateros": "Tomateros de Culiacán",
                "navojoa": "Mayos de Navojoa", "mayos": "Mayos de Navojoa",
                "mazatlan": "Venados de Mazatlán", "venados": "Venados de Mazatlán",
                "obregon": "Yaquis de Obregón", "yaquis": "Yaquis de Obregón",
                "jalisco": "Charros de Jalisco", "charros": "Charros de Jalisco",
                "caguas": "Criollos de Caguas", "criollos": "Criollos de Caguas",
                "santurce": "Cangrejeros de Santurce", "cangrejeros": "Cangrejeros de Santurce",
                "mayaguez": "Indios de Mayagüez", "indios": "Indios de Mayagüez",
                "carolina": "Gigantes de Carolina", "ponce": "Leones de Ponce"
            }
            for alias, target in sorted(alias_map.items(), key=lambda x: -len(x[0])):
                if re.search(rf"\b{re.escape(alias)}\b", low):
                    team = target
                    break

            if opponent:
                for alias, target in sorted(alias_map.items(), key=lambda x: -len(x[0])):
                    if re.search(rf"\b{re.escape(alias)}\b", opponent.lower()):
                        opponent = target
                        break

            if not team or len(team) < 2:
                team = "Tampa Bay Rays"

            res = self.tools.analyze_proposition(team=team, opponent=opponent, stat_type=stat_type, line=line, direction=direction)

            is_es = any(w in low for w in ("que", "opinas", "carreras", "goles", "puntos", "sobre", "mas", "menos", "hoy", "partido"))
            dir_label = ("Más de" if direction == "over" else "Menos de") if is_es else ("Over" if direction == "over" else "Under")

            p_pct = res["probability_pct"]
            fair_odds = res["fair_odds"]
            actual_team = res["team"]
            opp = res["opponent"]
            pitchers = res.get("pitchers") or {}
            p_str = f"{pitchers.get('home', '')} vs {pitchers.get('away', '')}" if isinstance(pitchers, dict) else str(pitchers)
            officials = res.get("officials", [])
            off_str = ", ".join(officials[:2]) if officials else "Panel oficial colegiado"
            injuries = res.get("injuries", {})
            inj_list = []
            if isinstance(injuries, dict):
                for side, injs in injuries.items():
                    if injs and isinstance(injs, list):
                        inj_list.extend(injs[:2])
            inj_str = "; ".join(inj_list[:3]) if inj_list else "Sin bajas críticas reportadas"
            weather = res.get("weather") or {}
            temp = weather.get("temp")
            cond = weather.get("condition") or "Cubierto/Estadio cerrado"

            if is_es:
                lines = [
                    f"📊 **Análisis Cuantitativo: {actual_team} - {dir_label} {line} {stat_type.capitalize()} vs {opp}**",
                    f"\nBasado en datos estadísticos de Poisson, forma reciente (rendimiento ofensivo), alineaciones y factores de juego:",
                    f"\n• 🎯 **Probabilidad Estimada por el Modelo:** **{p_pct}%**",
                    f"• 💰 **Cuota Justa Estimada:** **{fmt_odds(fair_odds)}** (Probabilidad pura sin margen del bookmaker)",
                    f"• 📈 **Tasa Ofensiva Proyectada:** **{res['expected_rate']}** {stat_type} para {actual_team}",
                    f"• ⚾ **Lanzadores / Jugadores Clave:** {p_str or 'Abridores proyectados'}",
                    f"• 🏥 **Reporte de Bajas / Lesiones:** {inj_str}",
                    f"• ⚖️ **Árbitro / Oficial:** {off_str}",
                    f"• ☀️ **Clima y Estadio:** {cond}{f' ({temp}°F)' if temp else ''}",
                    f"\n💡 **Evaluación de Valor (+EV) y Recomendación:**",
                    f"• Si tu casa de apuestas ofrece **{dir_label} {line}** a cuota superior a **{fmt_odds(fair_odds)}** (ej. cuota {res['sample_bookmaker_odds']}), obtienes una ventaja matemática positiva (**+{res['edge_pct']}% EV**).",
                    f"• **Gestión de Banca (Criterio de Kelly al 25%):** Stake recomendado del **{res['suggested_kelly_pct']}%** de tu banca para amortiguar la varianza."
                ]
            else:
                lines = [
                    f"📊 **Quantitative Analysis: {actual_team} - {dir_label} {line} {stat_type.capitalize()} vs {opp}**",
                    f"\nBased on quantitative data, recent offensive form, player matchups, and environmental splits:",
                    f"\n• 🎯 **Model Projected Probability:** **{p_pct}%**",
                    f"• 💰 **Fair Decimal Odds:** **{fmt_odds(fair_odds)}** (True fair price without bookmaker vig)",
                    f"• 📈 **Projected Scoring Rate:** **{res['expected_rate']}** {stat_type} for {actual_team}",
                    f"• ⚾ **Pitchers / Key Matchup:** {p_str or 'Probable starters'}",
                    f"• 🏥 **Injury & Lineup Report:** {inj_str}",
                    f"• ⚖️ **Officials / Umpire:** {off_str}",
                    f"• ☀️ **Weather & Venue:** {cond}{f' ({temp}°F)' if temp else ''}",
                    f"\n💡 **Value Analysis (+EV) & Recommendation:**",
                    f"• If your sportsbook offers **{dir_label} {line}** at odds higher than **{fmt_odds(fair_odds)}** (e.g. {res['sample_bookmaker_odds']}), this represents a positive expectation wager (**+{res['edge_pct']}% edge**).",
                    f"• **Bankroll Sizing (25% Fractional Kelly):** Recommended stake is **{res['suggested_kelly_pct']}%** of your bankroll."
                ]
            return "\n".join(lines)
        return None
    @staticmethod
    def _parse_stake(low: str) -> Optional[Tuple[float, float]]:
        pm = re.search(r"(\d+(?:\.\d+)?)\s*%", low)
        om = re.search(r"(?:at|@|odds)\s*(\d+\.\d+)", low) or re.search(r"(\d+\.\d+)", low)
        if pm and om:
            return float(pm.group(1)) / 100.0, float(om.group(1))
        return None

    def _value(self, low: str) -> str:
        sport = None
        for s in ("soccer", "basketball", "hockey", "baseball", "tennis", "mma", "volleyball"):
            if s in low:
                sport = s
        rows = self.tools.find_value(sport=sport)
        if not rows:
            return ("No hay apuestas +EV detectadas actualmente en partidos donde hayas ingresado tu cuota. "
                    "Haz clic derecho en cualquier cuota de la app para ingresar la de tu casa de apuestas y buscaré oportunidades de valor.")
        lines = [f"• **{r['event']}**: {r['selection']} ({r['market']}) - Modelo **{fmt_pct(r['model_prob'])}** "
                f"vs tu cuota **{fmt_odds(r['your_odds'])}** -> Ventaja: **+{r['edge_pct']}%**, Stake sugerido: **{r['kelly_stake_pct']}%**"
                for r in rows[:6]]
        return "💎 **Mejores Oportunidades de Valor (+EV):**\n\n" + "\n".join(lines) + f"\n\n{DISCLAIMER}"

    def _slip(self, session: Dict) -> str:
        legs = session.get("slip", [])
        if not legs:
            return ("Tu boleto de apuestas está vacío. "
                    "Haz clic en las cuotas de los partidos para agregar selecciones y pídeme analizarlo.")
        r = self.tools.price_parlay(legs)
        if "error" in r:
            return f"Error al procesar el boleto: {r['error']}"

        lines = ["📊 **Análisis y Feedback de tu Boleto Combinado:**\n"]
        for l in r["legs"]:
            lines.append(f"• **{l['event']}** | {l['selection']} ({l['market']}) -> Probabilidad: **{fmt_pct(l['prob'])}**")

        lines.append(f"\n🎲 **Evaluación Conjunta del Modelo:**")
        lines.append(f"• Probabilidad Real Conjunta: **{fmt_pct(r['true_probability'])}**")
        lines.append(f"• Cuota Justa Estimada: **{fmt_odds(r['fair_parlay_odds'])}**")
        lines.append(f"• Cuota Utilizada: **{fmt_odds(r['odds_used'])}**")

        ev = r['expected_value_pct']
        if ev > 0:
            lines.append(f"• Valor Esperado (+EV): **+{ev}%** (Ventaja matemática sobre la casa).")
        else:
            lines.append(f"• Valor Esperado: **{ev}%** (Margen a favor de la casa).")

        if r["notes"]:
            lines.append(f"\n🔗 **Análisis de Correlación:**")
            for n in r["notes"]:
                lines.append(f"• {n}")

        lines.append("\n⚠️ **Feedback de Riesgo & Gestión:**")
        p = r['true_probability']
        if p > 0.40:
            lines.append("• **Riesgo Conservador:** Probabilidad sólida. Stake recomendado: 2.0% - 3.5% de banca.")
        elif p > 0.15:
            lines.append("• **Riesgo Moderado:** Combinada estándar. Stake recomendado: 1.0% - 2.0% de banca.")
        else:
            lines.append("• **Riesgo Elevado (Alta Varianza):** Boleto de baja probabilidad. Recomendamos stake reducido (< 0.5% de banca).")

        return "\n".join(lines)

    def _referee(self, low: str) -> str:
        q = re.sub(r"\b(who|is|the|referee|ref|for|of|in|quien|es|el|arbitro|árbitro|de)\b", " ", low)
        hits = self.tools.find_event(q)
        if not hits:
            return "No encontré ese partido."
        e = hits[0]
        d = self.tools.event_markets(e["id"])
        ref = d.get("referee")
        return f"🧑‍⚖️ {e['home']} vs {e['away']}: El árbitro asignado es **{ref}**." if ref else f"No hay árbitro asignado aún para {e['home']} vs {e['away']}."

    def _match_lookup_and_opinion(self, text: str, low: str) -> str:
        clean_q = re.sub(r"\b(opinion|opinión|analisis|análisis|analizar|evaluar|dame|que|opinas|sobre|de|del|feedback|match|odds|cuotas)\b", " ", low)
        hits = self.tools.find_event(clean_q.strip() or text)
        if not hits:
            return ("No encontré ese equipo o partido. Prueba con el nombre de un equipo (ej: \"Barcelona\", \"Real Madrid\", \"Lakers\") "
                    "o escribe \"apuestas de valor\", \"analizar mi boleto\", o una consulta Kelly.")

        e = hits[0]
        d = self.tools.event_markets(e["id"])
        g = {x["id"]: x for x in d["groups"]}
        info = d.get("info", {})

        lines = [f"⚽ **Análisis Quant & Opinión: {e['home']} vs {e['away']}**"]
        lines.append(f"🏆 Competencia: **{e['competition']}** ({e['status'].upper()})")
        lines.append(f"🤖 Modelo: {info.get('model', 'Dixon-Coles')} (Confianza: {info.get('confidence', 'ok')})")
        lines.append("")

        if "1x2" in g:
            s = {x["id"]: x for x in g["1x2"]["selections"]}
            ph, pd, pa = s['home']['prob'], s['draw']['prob'], s['away']['prob']
            oh, od, oa = s['home']['odds'], s['draw']['odds'], s['away']['odds']
            lines.append("📊 **Probabilidades y Cuotas Justas (1X2):**")
            lines.append(f"• Victoria {e['home']}: **{fmt_pct(ph)}** (Cuota justa: **{fmt_odds(oh)}**)")
            lines.append(f"• Empate: **{fmt_pct(pd)}** (Cuota justa: **{fmt_odds(od)}**)")
            lines.append(f"• Victoria {e['away']}: **{fmt_pct(pa)}** (Cuota justa: **{fmt_odds(oa)}**)")
        elif "ml" in g:
            s = {x["id"]: x for x in g["ml"]["selections"]}
            k1, k2 = list(s.keys())
            lines.append("📊 **Probabilidades Moneyline:**")
            lines.append(f"• {s[k1]['label']}: **{fmt_pct(s[k1]['prob'])}** (Cuota justa: **{fmt_odds(s[k1]['odds'])}**)")
            lines.append(f"• {s[k2]['label']}: **{fmt_pct(s[k2]['prob'])}** (Cuota justa: **{fmt_odds(s[k2]['odds'])}**)")

        if info.get("expected_final"):
            ef = info["expected_final"]
            lines.append(f"\n🎯 **Marcador Esperado:** {ef[0]:.2f} - {ef[1]:.2f}")
        elif info.get("expected_total") is not None:
            lines.append(f"\n🎯 **Total Esperado:** {info['expected_total']:.1f}")

        lines.append("\n💡 **Opinión Quant & Recomendación:**")
        if "1x2" in g:
            ph = s['home']['prob']
            if ph > 0.60:
                lines.append(f"• **Dominio Local Esperado:** El modelo asigna **{fmt_pct(ph)}** de probabilidad a {e['home']}. Favorito sólido.")
                lines.append("• **Riesgo:** Bajo / Moderado.")
            elif ph < 0.40 and s['away']['prob'] < 0.40:
                lines.append("• **Partido Muy Parejo:** Probabilidades divididas con alto riesgo de empate. Varianza elevada.")
                lines.append("• **Recomendación:** Considera cubrimientos como Doble Oportunidad (1X/X2) o Empate No Válido (DNB).")
            else:
                fav = e['home'] if ph > s['away']['prob'] else e['away']
                fav_p = max(ph, s['away']['prob'])
                lines.append(f"• **Favorito Ligero:** {fav} lidera con **{fmt_pct(fav_p)}** de probabilidad.")

        user_val = self.tools.find_value(sport=e.get("sport"))
        match_vals = [v for v in user_val if v["event_id"] == e["id"]]
        if match_vals:
            lines.append("\n🔥 **Oportunidad de Valor (+EV) Registrada:**")
            for mv in match_vals:
                lines.append(f"• {mv['market']} -> {mv['selection']}: Tu cuota {fmt_odds(mv['your_odds'])} ofrece +{mv['edge_pct']}% de ventaja. Stake: {mv['kelly_stake_pct']}%")

        return "\n".join(lines)


# ============================================================================ online (LLM tool-calling)
class _BaseLLMChat:
    def __init__(self, tools: ToolBox, offline: OfflineChat):
        self.tools, self.offline = tools, offline

    def _dispatch(self, name: str, args: dict):
        fn = getattr(self.tools, name, None)
        if fn is None:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**args)
        except Exception as e:
            log.warning("tool %s failed: %s", name, e)
            return {"error": str(e)}


class AnthropicChat(_BaseLLMChat):
    URL = "https://api.anthropic.com/v1/messages"

    def reply(self, message: str, session: Dict) -> str:
        s = get_settings()
        history: List[dict] = session.setdefault("history", [])
        history.append({"role": "user", "content": message})
        headers = {"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        for _ in range(4):
            body = {"model": s.anthropic_model, "max_tokens": 800, "system": SYSTEM_PROMPT,
                   "tools": TOOL_SPECS, "messages": history}
            r = requests.post(self.URL, headers=headers, json=body, timeout=25)
            r.raise_for_status()
            data = r.json()
            content = data.get("content", [])
            history.append({"role": "assistant", "content": content})
            tool_uses = [b for b in content if b.get("type") == "tool_use"]
            if not tool_uses:
                text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
                return text or "..."
            results = []
            for tu in tool_uses:
                out = self._dispatch(tu["name"], tu.get("input", {}))
                results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": json.dumps(out, default=str)})
            history.append({"role": "user", "content": results})
        return "I ran out of tool-call turns - try asking a simpler question."


class GeminiChat(_BaseLLMChat):
    def url(self) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{get_settings().gemini_model}:generateContent"

    @staticmethod
    def _schema(spec: dict) -> dict:
        return {"name": spec["name"], "description": spec["description"], "parameters": spec["input_schema"]}

    def reply(self, message: str, session: Dict) -> str:
        s = get_settings()
        history: List[dict] = session.setdefault("history_g", [])
        history.append({"role": "user", "parts": [{"text": message}]})
        tools = [{"functionDeclarations": [self._schema(t) for t in TOOL_SPECS]}]
        for _ in range(4):
            body = {"contents": history, "tools": tools, "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]}}
            r = requests.post(f"{self.url()}?key={s.gemini_api_key}", json=body, timeout=25)
            r.raise_for_status()
            data = r.json()
            parts = data["candidates"][0]["content"]["parts"]
            history.append({"role": "model", "parts": parts})
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not calls:
                return "".join(p.get("text", "") for p in parts) or "..."
            resp_parts = []
            for c in calls:
                out = self._dispatch(c["name"], c.get("args", {}))
                resp_parts.append({"functionResponse": {"name": c["name"], "response": {"result": out}}})
            history.append({"role": "user", "parts": resp_parts})
        return "I ran out of tool-call turns - try asking a simpler question."


# ============================================================================ engine
class ChatEngine:
    def __init__(self, tools: ToolBox, max_sessions: int = 500, ttl_seconds: float = 86400.0):
        self.tools = tools
        self.offline = OfflineChat(tools)
        self.sessions: Dict[str, Dict] = defaultdict(dict)
        self.session_last_active: Dict[str, float] = {}
        self.max_sessions = max_sessions
        self.ttl_seconds = ttl_seconds

    def _get_session(self, session_id: str) -> Dict:
        now = time.time()
        self.session_last_active[session_id] = now
        if len(self.sessions) > self.max_sessions:
            self._cleanup_old_sessions(now)
        return self.sessions[session_id]

    def _cleanup_old_sessions(self, now: float) -> None:
        expired = [sid for sid, last in self.session_last_active.items() if now - last > self.ttl_seconds]
        for sid in expired:
            self.sessions.pop(sid, None)
            self.session_last_active.pop(sid, None)
        if len(self.sessions) > self.max_sessions:
            sorted_sessions = sorted(self.session_last_active.items(), key=lambda x: x[1])
            for sid, _ in sorted_sessions[:len(self.sessions) - self.max_sessions]:
                self.sessions.pop(sid, None)
                self.session_last_active.pop(sid, None)

    def _provider(self):
        s = get_settings()
        want = s.llm_provider
        if want == "offline":
            return None
        if (want in ("auto", "anthropic")) and s.anthropic_api_key:
            return AnthropicChat(self.tools, self.offline)
        if (want in ("auto", "gemini")) and s.gemini_api_key:
            return GeminiChat(self.tools, self.offline)
        return None

    def reply(self, session_id: str, message: str) -> Dict:
        session = self._get_session(session_id)
        provider = self._provider()
        used = "offline"
        try:
            if provider is not None:
                text = provider.reply(message, session)
                used = provider.__class__.__name__
            else:
                text = self.offline.reply(message, session)
        except Exception as e:
            log.warning("chat provider failed (%s), falling back to offline: %s", used, e)
            text = self.offline.reply(message, session)
            used = "offline (fallback)"
        return {"reply": text, "provider": used}

    def add_to_slip(self, session_id: str, event_id: str, key: str, odds: Optional[float] = None) -> List[dict]:
        session = self._get_session(session_id)
        slip = session.setdefault("slip", [])
        slip[:] = [l for l in slip if not (l["event_id"] == event_id and l["key"] == key)]
        leg = {"event_id": event_id, "key": key}
        if odds is not None:
            leg["odds"] = odds
        slip.append(leg)
        return slip

    def clear_slip(self, session_id: str) -> None:
        session = self._get_session(session_id)
        session["slip"] = []

    def get_slip(self, session_id: str) -> List[dict]:
        session = self._get_session(session_id)
        return session.get("slip", [])
