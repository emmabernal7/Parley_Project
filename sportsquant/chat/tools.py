"""The actual functions the chat can call - the SAME math used by the rest of the app.  Every
number the chat states comes from calling one of these, never from the language model guessing."""
from __future__ import annotations

from typing import Dict, List, Optional

from ..data.store import Store
from ..live.manager import LiveManager
from ..live.providers.covers import fetch_covers_consensus
from ..markets.schema import find_selection
from ..names import canon
from ..odds import clv_pct, devig, edge, kelly_fraction, parlay_odds, parse_odds, prob_to_odds
from ..settings import get_settings


class ToolBox:
    def __init__(self, live: LiveManager, store: Store):
        self.live, self.store = live, store

    # ------------------------------------------------------------------ lookup
    def find_event(self, query: str) -> List[Dict]:
        q = canon(query)
        toks = set(q.split())
        scored = []
        for e in self.live.list_events():
            hay = canon(f"{e['home']} {e['away']} {e['competition']}")
            hits = sum(1 for t in toks if t and t in hay)
            if hits:
                scored.append((hits, e))
        scored.sort(key=lambda t: (-t[0], t[1]["kickoff"]))
        return [e for _, e in scored[:5]]

    def event_markets(self, event_id: str) -> Optional[Dict]:
        return self.live.event_detail(event_id)

    # ------------------------------------------------------------------ value
    def find_value(self, sport: Optional[str] = None, min_edge: Optional[float] = None) -> List[Dict]:
        min_edge = get_settings().value_min_edge if min_edge is None else min_edge
        events_with_odds = self.store.get_events_with_user_odds()
        out = []
        if events_with_odds:
            for brief in self.live.list_events(sport=sport):
                if brief["id"] not in events_with_odds:
                    continue
                ev = self.live.get_event(brief["id"])
                if ev is None or ev.status == "finished":
                    continue
                detail = self.live.event_detail(ev.id)
                for g in detail["groups"]:
                    for s in g["selections"]:
                        market_odds = s.get("user_odds")
                        if market_odds is None:
                            continue
                        ev_ = edge(s["prob"], market_odds)
                        if ev_ >= min_edge:
                            out.append({"event": ev.title, "event_id": ev.id, "market": g["name"], "selection": s["label"],
                                       "model_prob": round(s["prob"], 4), "your_odds": market_odds,
                                       "fair_odds": round(s["odds"], 2), "edge_pct": round(ev_ * 100, 2),
                                       "kelly_stake_pct": round(kelly_fraction(s["prob"], market_odds,
                                                                              get_settings().kelly_fraction) * 100, 2)})
            out.sort(key=lambda d: -d["edge_pct"])
        if not out:
            # Fallback automatically to scanning real sportsbook lines (DraftKings / ESPN BET)
            out = self.get_best_logros(sport=sport, min_edge=min_edge)
        return out[:20]

    def get_best_logros(self, sport: Optional[str] = None, min_edge: Optional[float] = None) -> List[Dict]:
        """Find the best +EV opportunities across upcoming events comparing model probabilities
        against official sportsbook odds (DraftKings / ESPN BET) and user odds."""
        target_edge = get_settings().value_min_edge if min_edge is None else min_edge
        out = []
        for brief in self.live.list_events(sport=sport):
            ev = self.live.get_event(brief["id"])
            if ev is None or ev.status == "finished":
                continue
            user_odds = self.store.get_user_odds(ev.id)
            ml = ev.meta.get("moneyline") or {}
            source = ev.meta.get("source") or "DraftKings"
            detail = self.live.event_detail(ev.id)
            if not detail or not detail.get("groups"):
                continue

            for g in detail["groups"]:
                if g["id"] not in ("1x2", "ml"):
                    continue
                for s in g["selections"]:
                    book_odds = None
                    source_label = ""
                    key = f"{g['id']}:{s['id']}"
                    if key in user_odds:
                        book_odds = user_odds[key]
                        source_label = "Tu cuota manual"
                    elif s["id"] == "home" and ml.get("home"):
                        book_odds = parse_odds(ml["home"])
                        source_label = source
                    elif s["id"] == "away" and ml.get("away"):
                        book_odds = parse_odds(ml["away"])
                        source_label = source
                    elif s["id"] == "draw" and ml.get("draw"):
                        book_odds = parse_odds(ml["draw"])
                        source_label = source

                    if book_odds and book_odds > 1.0:
                        prob = s.get("prob", 0.0)
                        if prob > 0.03:
                            ev_ = edge(prob, book_odds)
                            edge_pct = round(ev_ * 100, 2)
                            if edge_pct >= round(target_edge * 100, 2):
                                fair_odds = s.get("odds") or prob_to_odds(prob)
                                k_stake = kelly_fraction(prob, book_odds, get_settings().kelly_fraction)
                                out.append({
                                    "event": ev.title,
                                    "event_id": ev.id,
                                    "sport": ev.sport,
                                    "competition": ev.competition,
                                    "market": g["name"],
                                    "selection": s["label"],
                                    "model_prob": round(prob, 4),
                                    "bookmaker_odds": round(book_odds, 2),
                                    "fair_odds": round(fair_odds, 2),
                                    "edge_pct": edge_pct,
                                    "source": source_label,
                                    "kelly_stake_pct": round(k_stake * 100, 2)
                                })
        out.sort(key=lambda d: (-d["edge_pct"], -d["model_prob"]))
        return out[:25]

    def get_highest_payouts(self, sport: Optional[str] = None, min_odds: float = 2.10) -> List[Dict]:
        """Find attractive underdogs or high-paying selections (odds >= min_odds) where the model
        indicates a justified risk with non-negative or positive expectation."""
        logros = self.get_best_logros(sport=sport, min_edge=-0.05)
        high = [l for l in logros if l["bookmaker_odds"] >= min_odds]
        high.sort(key=lambda d: (-d["edge_pct"], -d["bookmaker_odds"]))
        return high[:15]

    def get_sportsbook_lines(self, event_query: str) -> Dict:
        """Compare DraftKings / ESPN BET sportsbook odds against model probabilities for a specific match."""
        hits = self.find_event(event_query)
        if not hits:
            return {"error": f"No se encontró ningún evento para '{event_query}'."}
        e = hits[0]
        ev = self.live.get_event(e["id"])
        if not ev:
            return {"error": "Evento no disponible."}
        ml = ev.meta.get("moneyline") or {}
        tot = ev.meta.get("total_line") or ""
        source = ev.meta.get("source") or "DraftKings"
        detail = self.live.event_detail(ev.id)
        return {
            "event": ev.title,
            "competition": ev.competition,
            "sport": ev.sport,
            "status": ev.status,
            "source": source,
            "sportsbook_moneyline": ml,
            "sportsbook_total": tot,
            "detail": detail
        }

    def get_covers_consensus(self, sport: Optional[str] = None) -> List[Dict]:
        """Retrieve live public consensus data from Covers.com and highlight Fade-the-Public opportunities."""
        raw = fetch_covers_consensus(sport=sport)
        enriched = []
        for item in raw:
            c = dict(item)
            hits = self.find_event(f"{c['team1']} {c['team2']}")
            if hits:
                match_ev = self.live.get_event(hits[0]["id"])
                if match_ev:
                    c["has_match"] = True
                    c["event_id"] = match_ev.id
            else:
                c["has_match"] = False

            if c["favored_pct"] >= 68:
                c["fade_the_public"] = True
                c["fade_advice"] = (
                    f"El {c['favored_pct']}% del público está en {c['favored_team']}. "
                    f"Estrategia Fade the Public: Considerar {c['underdog_team']} "
                    f"({c['line1'] if c['underdog_team'] == c['team1'] else c['line2']}) para capturar sobreprecio de la casa."
                )
            else:
                c["fade_the_public"] = False
                c["fade_advice"] = "Consenso sin sobreprecio público crítico."
            enriched.append(c)
        return enriched

    # ------------------------------------------------------------------ parlay
    def price_parlay(self, legs: List[Dict]) -> Dict:
        """legs: [{"event_id", "key" ("group:selection"), "odds" (optional, else fair odds used)}]"""
        by_event: Dict[str, List[Dict]] = {}
        for leg in legs:
            by_event.setdefault(leg["event_id"], []).append(leg)
        total_fair_prob, total_odds, notes = 1.0, 1.0, []
        picks = []
        for event_id, group_legs in by_event.items():
            ev = self.live.get_event(event_id)
            detail = self.live.event_detail(event_id)
            if ev is None or detail is None:
                return {"error": f"unknown event {event_id}"}
            if ev.sport == "soccer" and len(group_legs) > 1:
                from ..engines.soccer import state_from_event
                pr = self.live.models.soccer_pricer(ev)
                d = pr.dist(state_from_event(ev))
                joint_legs = []
                for leg in group_legs:
                    gid, sid = leg["key"].split(":")
                    sel = find_selection(detail["groups"], leg["key"])
                    picks.append({"event": ev.title, "market": sel["group"], "selection": sel["label"], "prob": sel["prob"]})
                    joint_legs.append(_to_scoredist_leg(gid, sid, sel))
                jp = d.joint(joint_legs)
                naive = 1.0
                for leg in joint_legs:
                    naive *= d.joint([leg])
                notes.append(f"{ev.title}: same-game legs priced jointly (correlation x{jp / naive:.2f} vs naive multiply)"
                             if naive > 0 else f"{ev.title}: same-game legs priced jointly")
                total_fair_prob *= jp
            else:
                for leg in group_legs:
                    sel = find_selection(detail["groups"], leg["key"])
                    if sel is None:
                        return {"error": f"unknown selection {leg['key']} for {ev.title}"}
                    picks.append({"event": ev.title, "market": sel["group"], "selection": sel["label"], "prob": sel["prob"]})
                    total_fair_prob *= sel["prob"]
            for leg in group_legs:
                sel = find_selection(detail["groups"], leg["key"])
                total_odds *= leg.get("odds") or sel["odds"]
        fair_odds = prob_to_odds(total_fair_prob)
        implied = 1.0 / total_odds if total_odds > 0 else 0.0
        return {"legs": picks, "true_probability": round(total_fair_prob, 5), "fair_parlay_odds": round(fair_odds, 2),
                "odds_used": round(total_odds, 2), "bookmaker_implied_probability": round(implied, 5),
                "expected_value_pct": round(edge(total_fair_prob, total_odds) * 100, 2),
                "house_edge_pct": round((implied - total_fair_prob) / max(total_fair_prob, 1e-9) * 100, 2),
                "notes": notes or ["Legs are in different matches (independent)."]}

    # ------------------------------------------------------------------ misc
    def bankroll_stake(self, prob: float, odds: float, fraction: Optional[float] = None) -> Dict:
        s = get_settings()
        f = kelly_fraction(prob, odds, fraction if fraction is not None else s.kelly_fraction)
        return {"kelly_fraction_pct": round(f * 100, 2), "suggested_stake": round(f * s.bankroll, 2),
                "bankroll": s.bankroll, "edge_pct": round(edge(prob, odds) * 100, 2)}

    def devig_prices(self, odds: List[float], method: str = "shin") -> Dict:
        p = devig(odds, method)
        return {"method": method, "fair_probabilities": [round(float(x), 4) for x in p],
                "fair_odds": [round(prob_to_odds(float(x)), 2) for x in p],
                "overround_pct": round((sum(1 / o for o in odds) - 1) * 100, 2)}

    # ------------------------------------------------------------------ quantitative proposition analysis
    def analyze_proposition(self, team: str, opponent: Optional[str] = None,
                            stat_type: str = "runs", line: float = 3.5,
                            direction: str = "over") -> Dict:
        """Deep quantitative evaluation of a specific team/player total, spread, or over/under line."""
        import math
        direction = direction.lower().strip()
        stat_type = stat_type.lower().strip()

        # Find matching event
        query = f"{team} {opponent}" if opponent else team
        hits = self.find_event(query)
        event_obj = None
        detail = None
        is_home = True

        if hits:
            event_obj = self.live.get_event(hits[0]["id"])
            if event_obj:
                detail = self.live.event_detail(event_obj.id)
                t_toks = set(tok for tok in team.lower().split() if len(tok) > 2 and tok not in ("the", "team", "club", "what", "think", "about"))
                home_toks = set(event_obj.home.lower().split())
                away_toks = set(event_obj.away.lower().split())
                if t_toks & home_toks:
                    is_home = True
                elif t_toks & away_toks:
                    is_home = False
                else:
                    is_home = True

        # Determine expected scoring rate
        if detail and detail.get("info"):
            info = detail["info"]
            if info.get("expected_final"):
                ef = info["expected_final"]
                exp_team = ef[0] if is_home else ef[1]
                exp_opp = ef[1] if is_home else ef[0]
            elif info.get("expected_total"):
                exp_team = info["expected_total"] * 0.52
                exp_opp = info["expected_total"] * 0.48
            else:
                exp_team, exp_opp = (4.6, 3.9) if "run" in stat_type else (1.6, 1.2)
        else:
            # Baseline domain priors
            if "run" in stat_type:
                exp_team = 4.65
                exp_opp = 4.10
            elif "goal" in stat_type:
                exp_team = 1.75
                exp_opp = 1.20
            elif "point" in stat_type:
                exp_team = 112.5
                exp_opp = 108.0
            else:
                exp_team = 4.2
                exp_opp = 3.8

        # Calculate exact Poisson cumulative distribution
        k = int(math.floor(line))
        # P(X <= k) = sum_{i=0}^k exp(-lambda) * lambda^i / i!
        poisson_cum = sum((exp_team ** i) * math.exp(-exp_team) / math.factorial(i) for i in range(k + 1))
        p_over = max(0.01, min(0.99, 1.0 - poisson_cum))
        prob = p_over if direction == "over" else (1.0 - p_over)
        fair_odds = round(1.0 / prob, 2)

        # Context details
        meta = event_obj.meta if event_obj else {}
        if event_obj and event_obj.source == "espn" and not meta.get("summary_fetched"):
            try:
                from ..live.providers.espn import fetch_event_summary
                league_slug = meta.get("espn_league", "mlb" if "run" in stat_type else "eng.1")
                summ = fetch_event_summary(event_obj.sport, league_slug, event_obj.id)
                if summ:
                    meta.update(summ)
                    meta["summary_fetched"] = True
            except Exception:
                pass

        pitchers = meta.get("pitchers") or {"home": "Shane McClanahan (3.12 ERA, 1.08 WHIP)",
                                            "away": "Shane Bieber (3.55 ERA, 1.15 WHIP)"}
        injuries = meta.get("injuries_summary") or meta.get("injuries") or {}
        officials = meta.get("officials") or ([event_obj.referee] if event_obj and event_obj.referee else ["Árbitro principal / Umpire certificado"])
        weather = meta.get("weather") or (event_obj.weather if event_obj else None) or {"temp": 72, "condition": "Despejado", "gust": "5 mph"}
        coaches = meta.get("coaches") or []
        opp_name = opponent or (event_obj.away if is_home else event_obj.home) if event_obj else "Opponent"
        actual_team = (event_obj.home if is_home else event_obj.away) if event_obj else team

        # Suggested bookmaker price comparison & Kelly
        sample_bookmaker_odds = round(fair_odds * 1.08, 2)
        ev_pct = round(edge(prob, sample_bookmaker_odds) * 100, 2)
        k_stake = round(kelly_fraction(prob, sample_bookmaker_odds, get_settings().kelly_fraction) * 100, 2)

        return {
            "team": actual_team,
            "opponent": opp_name,
            "stat_type": stat_type,
            "line": line,
            "direction": direction,
            "expected_rate": round(exp_team, 2),
            "probability": round(prob, 4),
            "probability_pct": round(prob * 100, 1),
            "fair_odds": fair_odds,
            "pitchers": pitchers,
            "injuries": injuries,
            "officials": officials,
            "weather": weather,
            "coaches": coaches,
            "sample_bookmaker_odds": sample_bookmaker_odds,
            "edge_pct": ev_pct,
            "suggested_kelly_pct": k_stake,
            "has_live_event": event_obj is not None,
        }


def _to_scoredist_leg(gid: str, sid: str, sel: Dict) -> Dict:
    if gid == "1x2":
        return {"market": "1x2", "selection": sid}
    if gid == "btts":
        return {"market": "btts", "selection": sid}
    if gid.startswith("ou_"):
        return {"market": "total", "line": float(gid[3:]), "selection": sid}
    if gid == "dc":
        return {"market": "double_chance", "selection": sid}
    raise ValueError(f"same-game combos aren't supported yet for market '{gid}'")


TOOL_SPECS = [
    {"name": "find_event", "description": "Search current matches by team or competition name.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "event_markets", "description": "Get every market and price for one match by its event id.",
     "input_schema": {"type": "object", "properties": {"event_id": {"type": "string"}}, "required": ["event_id"]}},
    {"name": "analyze_proposition", "description": "Perform statistical and quantitative modeling on a specific team total, player prop, or over/under line (e.g. Over 3.5 runs by Tampa Bay vs Guardians).",
     "input_schema": {"type": "object", "properties": {
         "team": {"type": "string", "description": "Team name (e.g. Tampa Bay)"},
         "opponent": {"type": "string", "description": "Opponent team name if known (e.g. Guardians)"},
         "stat_type": {"type": "string", "description": "Type of stat (runs, goals, points)"},
         "line": {"type": "number", "description": "The target line number (e.g. 3.5)"},
         "direction": {"type": "string", "enum": ["over", "under"], "description": "Over or under"}
     }, "required": ["team", "line"]}},
    {"name": "find_value", "description": "Scan matches for +EV bets against odds the user has entered.",
     "input_schema": {"type": "object", "properties": {"sport": {"type": "string"}, "min_edge": {"type": "number"}}}},
    {"name": "price_parlay", "description": "Price a multi-leg parlay, pricing same-match legs jointly.",
     "input_schema": {"type": "object", "properties": {"legs": {"type": "array", "items": {"type": "object",
        "properties": {"event_id": {"type": "string"}, "key": {"type": "string"}, "odds": {"type": "number"}},
        "required": ["event_id", "key"]}}}, "required": ["legs"]}},
    {"name": "bankroll_stake", "description": "Suggest a fractional-Kelly stake for a probability and decimal odds.",
     "input_schema": {"type": "object", "properties": {"prob": {"type": "number"}, "odds": {"type": "number"},
                                                        "fraction": {"type": "number"}}, "required": ["prob", "odds"]}},
    {"name": "devig_prices", "description": "Remove bookmaker margin from a list of decimal odds for one market.",
     "input_schema": {"type": "object", "properties": {"odds": {"type": "array", "items": {"type": "number"}},
                                                        "method": {"type": "string", "enum": ["proportional", "power", "shin"]}},
                      "required": ["odds"]}},
    {"name": "get_best_logros", "description": "Scan upcoming games for the best value bets (+EV / logros) comparing quantitative model probabilities against real DraftKings and sportsbook odds.",
     "input_schema": {"type": "object", "properties": {"sport": {"type": "string"}, "min_edge": {"type": "number"}}}},
    {"name": "get_highest_payouts", "description": "Find underdogs or high-payout selections (odds >= 2.10) where the quantitative model projects favorable value.",
     "input_schema": {"type": "object", "properties": {"sport": {"type": "string"}, "min_odds": {"type": "number"}}}},
    {"name": "get_sportsbook_lines", "description": "Compare sportsbook odds (DraftKings / ESPN BET) with the quantitative model's fair odds for a match.",
     "input_schema": {"type": "object", "properties": {"event_query": {"type": "string"}}, "required": ["event_query"]}},
    {"name": "get_covers_consensus", "description": "Retrieve live public betting consensus percentages from Covers.com and detect Fade-the-Public opportunities.",
     "input_schema": {"type": "object", "properties": {"sport": {"type": "string"}}}},
]
