"""Poisson race engine for Baseball and Ice Hockey."""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from ...events import Event
from ...inplay.generic import race_dist, resolve_ties
from ...markets.schema import finalize, group, sel
from ...markets.scoredist import ScoreDist
from ..common import _hl, nearest_half


class PoissonRaceEngine:
    def __init__(self, sport: str, home: str, away: str, lam: float, mu: float, alpha: float = 0.0,
                 p_home_extra: float = 0.53, model_label: str = "Poisson ratings", confidence: str = "ok"):
        self.sport, self.home, self.away = sport, home, away
        self.lam, self.mu, self.alpha, self.p_ot = lam, mu, alpha, p_home_extra
        self.model_label, self.confidence = model_label, confidence

    def _remaining(self, ev: Event) -> Tuple[float, float, bool]:
        """(expected remaining runs/goals home, away, regulation_over)"""
        if ev.status == "finished":
            return 0.0, 0.0, True
        if ev.status != "live":
            return self.lam, self.mu, False
        if self.sport == "hockey":
            r = max(0.0, 1.0 - float(ev.clock.get("elapsed", 0.0)))
            return self.lam * r, self.mu * r, r <= 1e-9
        inning, half, outs = int(ev.clock.get("inning", 1)), ev.clock.get("half", "top"), int(ev.clock.get("outs", 0))
        away_out = (9 - inning) * 3 + ((3 - outs) if half == "top" else 0)
        home_out = (9 - inning) * 3 + ((3 - outs) if half == "bottom" else 3)
        away_out, home_out = max(0, away_out), max(0, home_out)
        return self.lam * home_out / 27.0, self.mu * away_out / 27.0, (home_out == 0 and away_out == 0)

    def _dists(self, ev: Event) -> Tuple[ScoreDist, ScoreDist]:
        lr, mr, over = self._remaining(ev)
        h, a = ev.score
        reg = race_dist(lr, mr, h, a, self.alpha)
        if ev.status == "finished" or over:
            fin = resolve_ties(reg, self.p_ot) if h == a else reg
        else:
            fin = resolve_ties(reg, self.p_ot)
        return reg, fin

    def info(self, ev: Event) -> Dict:
        reg, fin = self._dists(ev)
        return {"expected_final": list(reg.expected()), "model": self.model_label, "confidence": self.confidence}

    def markets(self, ev: Event) -> List[Dict]:
        H, A = self.home, self.away
        reg, fin = self._dists(ev)
        cur_t = ev.score[0] + ev.score[1]
        groups: List[Dict] = []
        ph = fin.p(fin.D > 0)
        ml_name = "Moneyline (incl. OT)" if self.sport == "hockey" else "Moneyline"
        groups.append(group("ml", ml_name, "main", [sel("home", H, ph), sel("away", A, 1 - ph)], kind="2way"))
        if self.sport == "hockey":
            a, b, c = reg.p_1x2()
            groups.append(group("reg", "60 Minutes Result", "main",
                                [sel("home", H, a), sel("draw", "Empate", b), sel("away", A, c)], kind="3way"))
        line_name, lid = ("Puck Line", "pl") if self.sport == "hockey" else ("Run Line", "rl")
        for L in (-1.5, 1.5):
            ph_l = fin.p(fin.D + L > 0)
            groups.append(group(f"{lid}_{L:+g}", f"{line_name} {_hl(L)}", "main",
                                [sel("home", f"{H} {_hl(L)}", ph_l, L), sel("away", f"{A} {_hl(-L)}", 1 - ph_l, -L)], kind="2way"))
        mean_t = sum(fin.expected())
        T0 = nearest_half(mean_t)
        for k in range(-3, 4):
            T = T0 + k
            if T <= cur_t:
                continue
            o = fin.p(fin.T > T)
            if o < 0.02 or o > 0.98:
                continue
            groups.append(group(f"tot_{T:g}", f"Total {'Goals' if self.sport == 'hockey' else 'Runs'} {T:g}",
                                "main" if k == 0 else "lines",
                                [sel("over", "Over", o, T), sel("under", "Under", 1 - o, T)], kind="2way"))
        for side, nm, arr in (("home", H, fin.X), ("away", A, fin.Y)):
            m = float((fin.G * arr).sum())
            T = nearest_half(m)
            if T > (ev.score[0] if side == "home" else ev.score[1]):
                o = fin.p(arr > T)
                groups.append(group(f"tt_{side}_{T:g}", f"{nm} Total {T:g}", "specials",
                                    [sel("over", "Over", o, T), sel("under", "Under", 1 - o, T)], kind="2way"))
        if self.sport == "baseball" and ev.status == "scheduled":
            f5 = race_dist(self.lam * 15 / 27.0, self.mu * 15 / 27.0, 0, 0, self.alpha)
            a, b, c = f5.p_1x2()
            groups.append(group("f5", "First 5 Innings Result", "specials",
                                [sel("home", H, a), sel("draw", "Empate", b), sel("away", A, c)], kind="3way",
                                note="Pre-match approximation (rates scaled to 5 innings)."))
        return finalize(groups)

    @staticmethod
    def headline(groups: Sequence[Dict]) -> Dict:
        out: Dict = {}
        for g in groups:
            if g["id"] == "ml":
                out["1x2"] = {s["id"]: s["prob"] for s in g["selections"]}
        return out
