"""Gaussian timed engine for Basketball and American Football."""
from __future__ import annotations

import math
from typing import Dict, List, Sequence

from ...events import Event
from ...inplay.generic import gaussian_final, p_ge, p_gt
from ...markets.schema import finalize, group, sel
from ..common import _hl, nearest_half


class GaussianEngine:
    def __init__(self, sport: str, home: str, away: str, margin: float, total: float, sd_margin: float,
                 sd_total: float, ot_frac: float, model_label: str = "Ridge ratings", confidence: str = "ok",
                 step: float = 1.0):
        self.sport, self.home, self.away = sport, home, away
        self.m, self.t, self.sm, self.st = margin, total, sd_margin, sd_total
        self.ot_frac, self.model_label, self.confidence, self.step = ot_frac, model_label, confidence, step

    def _final(self, ev: Event) -> Dict[str, float]:
        if ev.status == "finished":
            elapsed = 2.0
        elif ev.status == "live":
            elapsed = float(ev.clock.get("elapsed", 0.0))
        else:
            elapsed = 0.0
        h, a = ev.score
        return gaussian_final(self.m, self.t, self.sm, self.st, elapsed, h - a, h + a,
                              0.0 if ev.status == "finished" else self.ot_frac)

    def info(self, ev: Event) -> Dict:
        f = self._final(ev)
        return {"expected_margin": f["mu_m"], "expected_total": f["mu_t"], "model": self.model_label,
                "confidence": self.confidence}

    def markets(self, ev: Event) -> List[Dict]:
        H, A = self.home, self.away
        f = self._final(ev)
        mu_m, sd_m, mu_t, sd_t = f["mu_m"], f["sd_m"], f["mu_t"], f["sd_t"]
        groups: List[Dict] = []
        ph = p_ge(1, mu_m, sd_m)
        groups.append(group("ml", "Moneyline", "main", [sel("home", H, ph), sel("away", A, 1 - ph)], kind="2way"))

        L0 = -nearest_half(mu_m)
        for k in range(-5, 6):
            L = L0 + k * self.step
            L = nearest_half(L) if abs(L - round(L)) < 1e-9 else L
            pc = p_gt(-L, mu_m, sd_m)
            if pc < 0.02 or pc > 0.98:
                continue
            g = group(f"sp_{L:+g}", f"Spread {_hl(L)}", "main" if k == 0 else "lines",
                      [sel("home", f"{H} {_hl(L)}", pc, L), sel("away", f"{A} {_hl(-L)}", 1 - pc, -L)], kind="2way")
            groups.append(g)
        T0 = nearest_half(mu_t)
        for k in range(-4, 5):
            T = T0 + k * self.step * (2 if self.sport == "basketball" else 1)
            po = p_gt(T, mu_t, sd_t)
            if po < 0.02 or po > 0.98:
                continue
            groups.append(group(f"tot_{T:g}", f"Total Points {T:g}", "main" if k == 0 else "lines",
                                [sel("over", "Over", po, T), sel("under", "Under", 1 - po, T)], kind="2way"))
        sd_team = math.sqrt(sd_t ** 2 + sd_m ** 2) / 2.0
        for side, nm, mean in (("home", H, (mu_t + mu_m) / 2.0), ("away", A, (mu_t - mu_m) / 2.0)):
            T = nearest_half(mean)
            po = p_gt(T, mean, sd_team)
            groups.append(group(f"tt_{side}_{T:g}", f"{nm} Total Points {T:g}", "specials",
                                [sel("over", "Over", po, T), sel("under", "Under", 1 - po, T)], kind="2way"))
        w = 5 if self.sport == "basketball" else 7
        bands = [(1, w), (w + 1, 2 * w), (2 * w + 1, 3 * w), (3 * w + 1, 4 * w), (4 * w + 1, 5 * w), (5 * w + 1, 999)]
        sels = []
        for side, nm, sign in (("home", H, 1), ("away", A, -1)):
            for lo, hi in bands:
                mm = mu_m * sign
                p = p_ge(lo, mm, sd_m) - (p_ge(hi + 1, mm, sd_m) if hi < 900 else 0.0)
                lbl = f"{nm} {lo}-{hi}" if hi < 900 else f"{nm} {lo}+"
                sels.append(sel(f"{side}_{lo}", lbl, p))
        groups.append(group("wm", "Winning Margin", "specials", sels))
        return finalize(groups)

    @staticmethod
    def headline(groups: Sequence[Dict]) -> Dict:
        out: Dict = {}
        for g in groups:
            if g["id"] == "ml":
                out["1x2"] = {s["id"]: s["prob"] for s in g["selections"]}
        return out
