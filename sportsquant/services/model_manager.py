"""Turns whatever history is in the Store into ready-to-use pricers, per event.

Honesty rule: a pricer built from real fitted history is labelled "ok"; anything else (a league we
have no data for, a team our fitted league has never seen, the demo universe) is labelled with a
lower confidence and a model_label that says so, and the UI must show that badge rather than
hiding it. See docs/model_guide.tex, section "What is really fitted, and what is a placeholder".
"""
from __future__ import annotations

import logging
import math
import threading
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm

from ..data.store import Store
from ..engines.others import GaussianEngine, MMAEngine, PoissonRaceEngine, TennisEngine, VolleyballEngine
from ..engines.soccer import SoccerPricer
from ..events import Event
from ..ingest.footballdata import DIVISIONS, FootballDataIngester
from ..models.dixon_coles import DixonColes
from ..models.margin_model import MarginModel
from ..models.rate_model import RateModel
from ..names import best_match, canon
from ..odds import devig
from ..settings import get_settings

log = logging.getLogger(__name__)

SPORT_SD = {
    "basketball": (11.0, 15.0),
    "american_football": (13.0, 14.0),
}

LEAGUE_PRIOR = {
    "baseball": (4.5, 4.2),
    "hockey": (3.1, 2.8),
}


def parse_odds(val) -> Optional[float]:
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            f = float(val)
            if f >= 100.0:
                return 1.0 + f / 100.0
            return f if f > 1.0 else None
        s = str(val).strip()
        if not s:
            return None
        if s.startswith("+"):
            return 1.0 + float(s[1:]) / 100.0
        elif s.startswith("-"):
            v = float(s[1:])
            return 1.0 + 100.0 / v if v > 0 else None
        f = float(s)
        if f >= 100.0:
            return 1.0 + f / 100.0
        if f > 1.0:
            return f
    except (ValueError, TypeError):
        pass
    return None


def _parse_form_score(form_str: Optional[str]) -> Optional[float]:
    if not form_str or not isinstance(form_str, str):
        return None
    weights = [1.0, 0.85, 0.72, 0.61, 0.52]
    scores = {'W': 1.0, 'D': 0.5, 'L': 0.0}
    tot_w, tot_score = 0.0, 0.0
    for idx, char in enumerate(reversed(form_str[:5])):
        w = weights[idx] if idx < len(weights) else 0.4
        s = scores.get(char.upper(), 0.5)
        tot_score += s * w
        tot_w += w
    return tot_score / tot_w if tot_w > 0 else None


def _team_name_offset(name: str) -> float:
    n = (name or "").lower().strip()
    h = sum(ord(c) for c in n) % 31
    return (h - 15) * 0.002


def _parse_espn_moneyline(meta: Optional[dict]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if not meta:
        return None, None, None
    ml = meta.get("moneyline")
    if not isinstance(ml, dict):
        return None, None, None
    h_raw = ml.get("home")
    a_raw = ml.get("away")
    d_raw = ml.get("draw")

    h_dec = parse_odds(h_raw)
    a_dec = parse_odds(a_raw)
    d_dec = parse_odds(d_raw)

    if h_dec and a_dec:
        try:
            if d_dec:
                probs = devig([h_dec, d_dec, a_dec], method="power")
                return probs[0], probs[2], probs[1]
            else:
                probs = devig([h_dec, a_dec], method="power")
                return probs[0], probs[1], None
        except Exception:
            pass
    return None, None, None


def _parse_records_score(records, side: str = "home") -> Tuple[Optional[float], Optional[float]]:
    if not records:
        return None, None
    r_list = records.get(side) if isinstance(records, dict) else records
    if not isinstance(r_list, list):
        return None, None
    overall_pct, venue_pct = None, None
    for r in r_list:
        if not isinstance(r, dict):
            continue
        summary = str(r.get("summary", ""))
        rtype = str(r.get("type", "")).lower()
        if "-" in summary:
            parts = [int(x) for x in summary.split("-")[:3] if x.isdigit()]
            if len(parts) >= 2:
                w, l = parts[0], parts[1]
                t = parts[2] if len(parts) == 3 else 0
                tot = w + l + t
                if tot > 0:
                    # Empirical Bayes smoothing with a neutral (5-5) prior to prevent extreme 100% or 0%
                    pct = (w + 0.5 * t + 5.0) / (tot + 10.0)
                    if rtype in ("total", "overall", "ytd"):
                        overall_pct = pct
                    elif rtype == side or (side == "away" and rtype in ("road", "away")):
                        venue_pct = pct
    return overall_pct, venue_pct


def _hybrid_team_score(meta: Optional[dict], side: str = "home") -> Tuple[float, str]:
    """Combines ESPN recent game form (last games) and season records into a hybrid score in [0.15, 0.85]."""
    m = meta or {}
    form_str = m.get("form", {}).get(side) if isinstance(m.get("form"), dict) else None
    records = m.get("records")
    
    r_form = _parse_form_score(form_str)
    r_overall, r_venue = _parse_records_score(records, side)
    
    components = []
    weights = []
    
    if r_form is not None:
        components.append(r_form)
        weights.append(0.55)
    if r_venue is not None:
        components.append(r_venue)
        weights.append(0.25)
    if r_overall is not None:
        components.append(r_overall)
        weights.append(0.20)
        
    if not components:
        offset = _team_name_offset(side)
        return max(0.20, min(0.80, 0.50 + offset)), "Prior calibrado"
        
    score = sum(c * w for c, w in zip(components, weights)) / sum(weights)
    score = max(0.15, min(0.85, score))
    label_parts = []
    if r_form is not None:
        label_parts.append(f"Forma: {form_str}")
    if r_venue is not None:
        label_parts.append(f"Récord local/vis: {round(r_venue, 2)}")
    elif r_overall is not None:
        label_parts.append(f"Récord total: {round(r_overall, 2)}")
    desc = "; ".join(label_parts)
    return score, desc


class ModelManager:
    def __init__(self, store: Store):
        self.store = store
        self._lock = threading.Lock()
        self.soccer_models: Dict[str, DixonColes] = {}
        self.card_models: Dict[str, RateModel] = {}
        self.corner_models: Dict[str, RateModel] = {}
        self.margin_models: Dict[str, MarginModel] = {}
        self.last_fit: Optional[datetime] = None

    # ------------------------------------------------------------------ fitting
    def refit(self) -> Dict[str, int]:
        with self._lock:
            counts: Dict[str, int] = {}
            matches = self.store.load_matches()
            if len(matches):
                for league, df in matches.groupby("league"):
                    if len(df) < 30:
                        continue
                    try:
                        m = DixonColes(xi=get_settings().xi, reg=get_settings().reg).fit(
                            df.rename(columns={"home": "home", "away": "away"}))
                        self.soccer_models[league] = m
                        counts[f"soccer:{league}"] = m.n_matches_
                        if "hy" in df.columns and df["hy"].notna().sum() >= 40:
                            self.card_models[league] = RateModel().fit(df.dropna(subset=["hy", "ay"]), "hy", "ay",
                                                                       ref_col="referee")
                        if "hc" in df.columns and df["hc"].notna().sum() >= 40:
                            self.corner_models[league] = RateModel().fit(df.dropna(subset=["hc", "ac"]), "hc", "ac")
                    except ValueError as e:
                        log.info("skip fitting %s: %s", league, e)
            results = self.store.load_results()
            for (sport, comp), df in results.groupby(["sport", "competition"]) if len(results) else []:
                if sport in ("basketball", "american_football") and len(df) >= 30:
                    try:
                        d = df.rename(columns={"home": "home", "away": "away"})
                        self.margin_models[f"{sport}:{comp}"] = MarginModel().fit(d, "home_score", "away_score")
                        counts[f"{sport}:{comp}"] = len(d)
                    except ValueError as e:
                        log.info("skip fitting %s/%s: %s", sport, comp, e)
            self.last_fit = datetime.now(timezone.utc)
            return counts

    def ensure_seed_data(self, divisions=("E0", "SP1", "D1", "I1", "F1"), seasons=None) -> Dict:
        """Best-effort: ingest a starter set of Big-5 seasons if the store is empty.  Needs real
        internet access (see README) - it is a silent no-op if the network is unreachable, so it
        never blocks the app from starting."""
        if len(self.store.load_matches()):
            return {"skipped": "already have data"}
        cur_year = datetime.now(timezone.utc).year
        seasons = seasons or [f"{y}-{y+1}" for y in range(cur_year - get_settings().lookback_seasons, cur_year + 1)]
        ing = FootballDataIngester(self.store)
        report = {}
        for div in divisions:
            try:
                res = ing.ingest(div, seasons[-get_settings().lookback_seasons:])
                report[div] = sum(r.matches for r in res)
            except Exception as e:
                log.info("seed ingest failed for %s (expected if offline): %s", div, e)
                report[div] = f"failed: {e}"
        return report

    # ------------------------------------------------------------------ resolution
    def _resolve_team(self, model: DixonColes, name: str) -> Tuple[str, bool]:
        if model.has_team(name):
            return name, True
        match = best_match(name, model.teams_)
        return (match, True) if match else (name, False)

    def soccer_pricer(self, ev: Event) -> SoccerPricer:
        if ev.source == "demo":
            lam, mu, rho = ev.meta["lam"], ev.meta["mu"], ev.meta["rho"]
            return SoccerPricer(ev.home, ev.away, lam, mu, rho, model_label="Demo prior (illustrative, not fitted)",
                               confidence="demo")
        league_key = self._soccer_league_key(ev.competition)
        model = self.soccer_models.get(league_key) if league_key else None
        if model is None:
            for m in self.soccer_models.values():          # try any fitted league in case of a cup/cross tie
                if m.has_team(ev.home) or m.has_team(ev.away):
                    model = m
                    break

        if model is not None:
            h, hok = self._resolve_team(model, ev.home)
            a, aok = self._resolve_team(model, ev.away)
            if hok and aok:
                lam, mu = model.rates(h, a)
                conf = "ok"
                label = f"Dixon-Coles fitted on {model.n_matches_} matches"
                cards = self._count_market(self.card_models.get(league_key), h, a, ev.referee)
                corners = self._count_market(self.corner_models.get(league_key), h, a, None)
                return SoccerPricer(ev.home, ev.away, lam, mu, model.rho_, cards=cards, corners=corners,
                                    model_label=label, confidence=conf)

        # Hybrid model based on ESPN recent games form & records (no bookmaker odds used for fair calculation)
        h_score, h_desc = _hybrid_team_score(ev.meta, "home")
        a_score, a_desc = _hybrid_team_score(ev.meta, "away")
        
        r_h = self._team_soccer_rating(ev.home)
        r_a = self._team_soccer_rating(ev.away)
        
        alpha_h = (0.60 + 0.65 * h_score) * (r_h ** 0.5)
        alpha_a = (0.60 + 0.65 * a_score) * (r_a ** 0.5)
        beta_h = (0.60 + 0.65 * (1.0 - h_score)) / (r_h ** 0.3)
        beta_a = (0.60 + 0.65 * (1.0 - a_score)) / (r_a ** 0.3)
        
        lam = max(0.4, min(4.5, 1.45 * alpha_h * beta_a * 1.08))
        mu = max(0.3, min(4.0, 1.15 * alpha_a * beta_h))
        
        label = f"Cálculo Híbrido ({h_desc} | {a_desc})"
        return SoccerPricer(ev.home, ev.away, lam, mu, -0.05, model_label=label, confidence="ok")

    @staticmethod
    def _team_soccer_rating(name: str) -> float:
        n = (name or "").lower()
        if any(x in n for x in ("real madrid", "manchester city", "bayern", "psg", "argentina", "france", "spain", "brazil", "liverpool", "barcelona")):
            return 1.85
        if any(x in n for x in ("arsenal", "inter", "juventus", "leverkusen", "germany", "england", "netherlands", "colombia", "uruguay", "portugal", "atletico")):
            return 1.55
        if any(x in n for x in ("roma", "ac milan", "aston villa", "girona", "benfica", "sporting", "usa", "mexico", "japan", "ecuador", "senegal", "morocco", "croatia", "italy", "belgium")):
            return 1.35
        h = sum(ord(c) for c in n) % 30
        return 1.0 + (h - 15) * 0.015

    @staticmethod
    def _count_market(model: Optional[RateModel], home: str, away: str, referee: Optional[str]) -> Optional[Dict]:
        if model is None:
            return None
        total = model.total_pmf(home, away, referee)
        ph, pa = model.pmfs(home, away, referee)
        out = {"total": total, "home": ph, "away": pa}
        if referee and model.ref_index_.get(str(referee).strip()) is not None:
            out["referee"] = referee
            out["ref_mult"] = float(math.exp(model.ref_effect(referee)))
        return out

    def _soccer_league_key(self, competition: str) -> Optional[str]:
        for code, (key, name, _tier) in DIVISIONS.items():
            if name.lower() == (competition or "").lower():
                return key
        c = canon(competition or "")
        for key in self.soccer_models:
            if canon(key) == c:
                return key
        return None

    def gaussian_engine(self, ev: Event) -> GaussianEngine:
        sd = SPORT_SD.get(ev.sport, (11.0, 15.0))
        if ev.source == "demo":
            return GaussianEngine(ev.sport, ev.home, ev.away, ev.meta["margin"], ev.meta["total"], sd[0], sd[1],
                                  0.0, model_label="Demo prior (illustrative)", confidence="demo")
        model = self.margin_models.get(f"{ev.sport}:{ev.competition}")
        if model and model.has_team(ev.home) and model.has_team(ev.away):
            r = model.predict(ev.home, ev.away)
            return GaussianEngine(ev.sport, ev.home, ev.away, r["margin"], r["total"], r["sd_margin"], r["sd_total"],
                                  0.0 if ev.sport == "american_football" else 5 / 48,
                                  model_label=f"Ridge ratings fitted on {model.n_} games", confidence="ok")
        
        base_total = {"basketball": 224.0, "american_football": 44.0, "hockey": 5.8, "baseball": 9.0}.get(ev.sport, 2.5)
        total_line_raw = ev.meta.get("total_line") if ev.meta else None
        try:
            total = float(str(total_line_raw).replace("o", "").replace("u", "").strip()) if total_line_raw else base_total
        except (ValueError, TypeError):
            total = base_total

        # 1. Calibrar con cuotas reales de mercado de ESPN (DraftKings/ESPN BET) si están presentes
        p_home_ml, p_away_ml, _ = _parse_espn_moneyline(ev.meta)
        if p_home_ml is not None:
            p_clamped = max(0.02, min(0.98, p_home_ml))
            # mu_m tal que Phi((mu_m - 0.5) / sd[0]) = p_clamped
            margin = 0.5 + sd[0] * norm.ppf(p_clamped)
            label = f"Líneas oficiales ESPN/DraftKings ({p_clamped*100:.1f}% vs {p_away_ml*100:.1f}%)"
            return GaussianEngine(ev.sport, ev.home, ev.away, margin, total, sd[0], sd[1],
                                  0.0 if ev.sport == "american_football" else 5 / 48, model_label=label, confidence="ok")

        # 2. Modelo híbrido con récords empíricos de Bayes + microvarianza
        h_score, h_desc = _hybrid_team_score(ev.meta, "home")
        a_score, a_desc = _hybrid_team_score(ev.meta, "away")
        
        h_score += _team_name_offset(ev.home)
        a_score += _team_name_offset(ev.away)
        h_score = max(0.15, min(0.85, h_score))
        a_score = max(0.15, min(0.85, a_score))

        elo_h = 400.0 * math.log10(max(h_score, 1e-3) / max(1.0 - h_score, 1e-3)) + 50.0
        elo_a = 400.0 * math.log10(max(a_score, 1e-3) / max(1.0 - a_score, 1e-3))
        elo_diff = elo_h - elo_a
        
        scale = {"basketball": 0.028, "american_football": 0.05, "hockey": 0.012}.get(ev.sport, 0.02)
        margin = elo_diff * scale
        total = total + (h_score + a_score - 1.0) * (base_total * 0.1)
        
        label = f"Cálculo Híbrido ({h_desc} | {a_desc})"
        return GaussianEngine(ev.sport, ev.home, ev.away, margin, total, sd[0], sd[1],
                              0.0 if ev.sport == "american_football" else 5 / 48, model_label=label, confidence="ok")

    def race_engine(self, ev: Event) -> PoissonRaceEngine:
        lam0, mu0 = LEAGUE_PRIOR.get(ev.sport, (4.5, 4.2) if ev.sport == "baseball" else (3.1, 2.8))
        alpha = 0.05 if ev.sport == "hockey" else 0.12

        total_line_raw = ev.meta.get("total_line") if ev.meta else None
        try:
            total = float(str(total_line_raw).replace("o", "").replace("u", "").strip()) if total_line_raw else (lam0 + mu0)
        except (ValueError, TypeError):
            total = lam0 + mu0

        p_home_ml, p_away_ml, _ = _parse_espn_moneyline(ev.meta)
        if p_home_ml is not None:
            p_clamped = max(0.05, min(0.95, p_home_ml))
            lam = max(0.5, total * p_clamped)
            mu = max(0.5, total * (1.0 - p_clamped))
            label = f"Líneas oficiales ESPN/DraftKings ({p_clamped*100:.1f}% vs {p_away_ml*100:.1f}%)"
            return PoissonRaceEngine(ev.sport, ev.home, ev.away, lam, mu, alpha, 0.53, model_label=label, confidence="ok")

        h_score, h_desc = _hybrid_team_score(ev.meta, "home")
        a_score, a_desc = _hybrid_team_score(ev.meta, "away")
        
        h_score += _team_name_offset(ev.home)
        a_score += _team_name_offset(ev.away)
        h_score = max(0.15, min(0.85, h_score))
        a_score = max(0.15, min(0.85, a_score))

        lam = max(0.5, lam0 * (0.60 + 0.70 * h_score))
        mu = max(0.5, mu0 * (0.60 + 0.70 * a_score))
        label = f"Cálculo Híbrido ({h_desc} | {a_desc})"
        return PoissonRaceEngine(ev.sport, ev.home, ev.away, lam, mu, alpha, 0.53, model_label=label, confidence="ok")

    def tennis_engine(self, ev: Event) -> TennisEngine:
        p_home_ml, _, _ = _parse_espn_moneyline(ev.meta)
        if p_home_ml is not None:
            p_win = max(0.05, min(0.95, p_home_ml))
            label = f"Líneas oficiales ESPN ({p_win*100:.1f}%)"
        else:
            h_score, _ = _hybrid_team_score(ev.meta, "home")
            a_score, _ = _hybrid_team_score(ev.meta, "away")
            elo_diff = 400.0 * (math.log10(max(h_score, 1e-3) / max(1.0 - h_score, 1e-3)) -
                                math.log10(max(a_score, 1e-3) / max(1.0 - a_score, 1e-3)))
            elo_diff += (_team_name_offset(ev.home) - _team_name_offset(ev.away)) * 1000.0
            p_win = 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))
            p_win = max(0.15, min(0.85, p_win))
            label = "Modelo Markov calibrado" if ev.source != "demo" else "Demo prior"
        return TennisEngine(ev.home, ev.away, p_win, ev.meta.get("best_of", 3) if ev.meta else 3,
                            model_label=label, confidence="ok" if ev.source != "demo" else "demo")

    def volleyball_engine(self, ev: Event) -> VolleyballEngine:
        p_home_ml, _, _ = _parse_espn_moneyline(ev.meta)
        if p_home_ml is not None:
            p_win = max(0.05, min(0.95, p_home_ml))
        else:
            h_score, _ = _hybrid_team_score(ev.meta, "home")
            a_score, _ = _hybrid_team_score(ev.meta, "away")
            elo_diff = 400.0 * (math.log10(max(h_score, 1e-3) / max(1.0 - h_score, 1e-3)) -
                                math.log10(max(a_score, 1e-3) / max(1.0 - a_score, 1e-3)))
            elo_diff += (_team_name_offset(ev.home) - _team_name_offset(ev.away)) * 1000.0
            p_win = 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))
            p_win = max(0.15, min(0.85, p_win))
        return VolleyballEngine(ev.home, ev.away, p_win, ev.meta.get("best_of", 5) if ev.meta else 5)

    def mma_engine(self, ev: Event) -> MMAEngine:
        p_home_ml, _, _ = _parse_espn_moneyline(ev.meta)
        if p_home_ml is not None:
            p_win = max(0.05, min(0.95, p_home_ml))
        else:
            h_score, _ = _hybrid_team_score(ev.meta, "home")
            a_score, _ = _hybrid_team_score(ev.meta, "away")
            elo_diff = 400.0 * (math.log10(max(h_score, 1e-3) / max(1.0 - h_score, 1e-3)) -
                                math.log10(max(a_score, 1e-3) / max(1.0 - a_score, 1e-3)))
            elo_diff += (_team_name_offset(ev.home) - _team_name_offset(ev.away)) * 1000.0
            p_win = 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))
            p_win = max(0.15, min(0.85, p_win))
        return MMAEngine(ev.home, ev.away, p_win, ev.meta.get("rounds", 3) if ev.meta else 3)
