"""Pricing engines for every sport except soccer.

Each engine turns a handful of model numbers (expected margin / goals / win probability) plus the
live state of an Event into market groups with the same shape as soccer's.
"""
from __future__ import annotations

import hashlib
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..events import Event
from ..inplay.generic import gaussian_final, p_ge, p_gt, race_dist, resolve_ties
from ..markets.schema import finalize, group, sel
from ..markets.scoredist import ScoreDist
from ..models.racket import (rally_prob_for_win, serve_probs_for_win, set_dist, tennis_match, volleyball_match)


def nearest_half(x: float) -> float:
    return float(round(x - 0.5) + 0.5)


def _hl(x: float) -> str:
    return f"{x:+g}"


# ============================================================================ Gaussian: basketball, NFL
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


# ============================================================================ Poisson race: hockey, baseball
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


# ============================================================================ Tennis
class TennisEngine:
    def __init__(self, a: str, b: str, p_win_a: float, best_of: int = 3, base_serve: float = 0.64,
                 model_label: str = "Elo + Markov chain", confidence: str = "ok"):
        self.a, self.b, self.best_of = a, b, best_of
        self.pa, self.pb = serve_probs_for_win(p_win_a, base_serve, best_of)
        self.model_label, self.confidence = model_label, confidence

    def _match(self, ev: Event) -> Dict:
        lv = ev.live
        if ev.status == "live" and lv.get("sets") is not None:
            sets = tuple(lv.get("sets", (0, 0)))
            games = tuple(lv.get("games", (0, 0)))
            pts = lv.get("points")
            first_a = lv.get("set_first_a")
            if first_a is None:
                first_a = True
            return tennis_match(self.pa, self.pb, self.best_of, first_a=True, sets=sets,
                                games_before=int(lv.get("games_before", 0)), cur_games=games, cur_first_a=bool(first_a),
                                game_pts=tuple(pts) if pts else None)
        m1 = tennis_match(self.pa, self.pb, self.best_of, first_a=True)
        m2 = tennis_match(self.pa, self.pb, self.best_of, first_a=False)
        def avg(d1, d2):
            keys = set(d1) | set(d2)
            return {k: 0.5 * (d1.get(k, 0) + d2.get(k, 0)) for k in keys}
        return {"win_a": 0.5 * (m1["win_a"] + m2["win_a"]), "set_scores": avg(m1["set_scores"], m2["set_scores"]),
                "games": avg(m1["games"], m2["games"])}

    def info(self, ev: Event) -> Dict:
        return {"model": self.model_label, "confidence": self.confidence, "serve_probs": [self.pa, self.pb]}

    def markets(self, ev: Event) -> List[Dict]:
        A, B = self.a, self.b
        m = self._match(ev)
        pa = m["win_a"]
        groups = [group("ml", "Match Winner", "main", [sel("a", A, pa), sel("b", B, 1 - pa)], kind="2way")]
        need = self.best_of // 2 + 1
        ss = m["set_scores"]
        sets_sel = []
        for (sa, sb), q in sorted(ss.items(), key=lambda kv: (-kv[0][0], kv[0][1])):
            if sa == need:
                sets_sel.append(sel(f"a_{sa}{sb}", f"{A} {sa}-{sb}", q))
        for (sa, sb), q in sorted(ss.items(), key=lambda kv: (kv[0][0], -kv[0][1])):
            if sb == need:
                sets_sel.append(sel(f"b_{sa}{sb}", f"{B} {sb}-{sa}", q))
        groups.append(group("set_score", "Set Betting", "main", sets_sel))
        tot_sets_line = 2.5 if self.best_of == 3 else 3.5
        po = sum(q for (sa, sb), q in ss.items() if sa + sb > tot_sets_line)
        groups.append(group(f"sets_{tot_sets_line:g}", f"Total Sets {tot_sets_line:g}", "main",
                            [sel("over", "Over", po, tot_sets_line), sel("under", "Under", 1 - po, tot_sets_line)], kind="2way"))
        for L in (-1.5, 1.5):
            pc = sum(q for (sa, sb), q in ss.items() if (sa - sb) + L > 0)
            groups.append(group(f"sh_{L:+g}", f"Set Handicap {_hl(L)}", "lines",
                                [sel("a", f"{A} {_hl(L)}", pc, L), sel("b", f"{B} {_hl(-L)}", 1 - pc, -L)], kind="2way"))
        games = m["games"]
        mean_g = sum(g * q for g, q in games.items())
        G0 = nearest_half(mean_g)
        for k in range(-3, 4):
            T = G0 + k
            po = sum(q for g, q in games.items() if g > T)
            if po < 0.02 or po > 0.98:
                continue
            groups.append(group(f"games_{T:g}", f"Total Games {T:g}", "main" if k == 0 else "lines",
                                [sel("over", "Over", po, T), sel("under", "Under", 1 - po, T)], kind="2way"))
        if ev.status == "scheduled":
            p1 = 0.5 * (sum(q for (x, y), q in set_dist(self.pa, self.pb, True).items() if x > y)
                        + sum(q for (x, y), q in set_dist(self.pa, self.pb, False).items() if x > y))
            groups.append(group("first_set", "First Set Winner", "specials", [sel("a", A, p1), sel("b", B, 1 - p1)], kind="2way"))
        return finalize(groups)

    @staticmethod
    def headline(groups: Sequence[Dict]) -> Dict:
        out: Dict = {}
        for g in groups:
            if g["id"] == "ml":
                s = {x["id"]: x["prob"] for x in g["selections"]}
                out["1x2"] = {"home": s["a"], "away": s["b"]}
        return out


# ============================================================================ Volleyball
class VolleyballEngine:
    def __init__(self, a: str, b: str, p_win_a: float, best_of: int = 5, model_label: str = "Elo + rally Markov chain",
                 confidence: str = "ok"):
        self.a, self.b, self.best_of = a, b, best_of
        self.p = rally_prob_for_win(p_win_a, best_of)
        self.model_label, self.confidence = model_label, confidence

    def info(self, ev: Event) -> Dict:
        return {"model": self.model_label, "confidence": self.confidence, "rally_prob": self.p}

    def markets(self, ev: Event) -> List[Dict]:
        A, B = self.a, self.b
        lv = ev.live
        if ev.status == "live" and lv.get("sets") is not None:
            m = volleyball_match(self.p, self.best_of, tuple(lv["sets"]), tuple(lv.get("points", (0, 0))), True,
                                 int(lv.get("points_before", 0)))
        else:
            m = volleyball_match(self.p, self.best_of)
        pa = m["win_a"]
        need = self.best_of // 2 + 1
        ss = m["set_scores"]
        groups = [group("ml", "Match Winner", "main", [sel("a", A, pa), sel("b", B, 1 - pa)], kind="2way")]
        sets_sel = [sel(f"a_{sa}{sb}", f"{A} {sa}-{sb}", q) for (sa, sb), q in sorted(ss.items()) if sa == need]
        sets_sel += [sel(f"b_{sa}{sb}", f"{B} {sb}-{sa}", q) for (sa, sb), q in sorted(ss.items()) if sb == need]
        groups.append(group("set_score", "Set Betting", "main", sets_sel))
        line = 3.5
        po = sum(q for (sa, sb), q in ss.items() if sa + sb > line)
        groups.append(group(f"sets_{line:g}", f"Total Sets {line:g}", "main",
                            [sel("over", "Over", po, line), sel("under", "Under", 1 - po, line)], kind="2way"))
        for L in (-1.5, 1.5):
            pc = sum(q for (sa, sb), q in ss.items() if (sa - sb) + L > 0)
            groups.append(group(f"sh_{L:+g}", f"Set Handicap {_hl(L)}", "lines",
                                [sel("a", f"{A} {_hl(L)}", pc, L), sel("b", f"{B} {_hl(-L)}", 1 - pc, -L)], kind="2way"))
        pts = m["points"]
        mean_p = sum(p * q for p, q in pts.items())
        P0 = nearest_half(mean_p)
        for k in range(-3, 4):
            T = P0 + 2 * k
            po = sum(q for p, q in pts.items() if p > T)
            if 0.02 < po < 0.98:
                groups.append(group(f"pts_{T:g}", f"Total Points {T:g}", "main" if k == 0 else "lines",
                                    [sel("over", "Over", po, T), sel("under", "Under", 1 - po, T)], kind="2way"))
        return finalize(groups)

    @staticmethod
    def headline(groups: Sequence[Dict]) -> Dict:
        return TennisEngine.headline(groups)


# ============================================================================ MMA
class MMAEngine:
    KO, SUB, DEC = 0.45, 0.18, 0.37          # prior method mix for a 3-round fight (before the outcome is known)

    def __init__(self, a: str, b: str, p_win_a: float, rounds: int = 3, model_label: str = "Elo", confidence: str = "ok"):
        self.a, self.b, self.p, self.rounds = a, b, float(min(0.995, max(0.005, p_win_a))), rounds
        self.model_label, self.confidence = model_label, confidence

    def info(self, ev: Event) -> Dict:
        return {"model": self.model_label, "confidence": self.confidence}

    def markets(self, ev: Event) -> List[Dict]:
        A, B, p = self.a, self.b, self.p
        dist = 0.40 if self.rounds == 3 else 0.30            # P(fight goes the distance): prior
        finish = 1.0 - dist
        ko, sub = finish * self.KO / (self.KO + self.SUB), finish * self.SUB / (self.KO + self.SUB)
        groups = [group("ml", "Fight Winner", "main", [sel("a", A, p), sel("b", B, 1 - p)], kind="2way")]
        sels = []
        for side, nm, w in (("a", A, p), ("b", B, 1 - p)):
            sels += [sel(f"{side}_ko", f"{nm} by KO/TKO", w * ko), sel(f"{side}_sub", f"{nm} by Submission", w * sub),
                     sel(f"{side}_dec", f"{nm} by Decision", w * dist)]
        groups.append(group("method", "Method of Victory", "main", sels))
        groups.append(group("distance", "Fight Goes the Distance", "main",
                            [sel("yes", "Yes", dist), sel("no", "No", finish)], kind="2way"))
        q = 1.0 - dist ** (1.0 / self.rounds)                 # per-round finish probability
        for k in range(1, self.rounds):
            o = (1 - q) ** k
            groups.append(group(f"rounds_{k + 0.5:g}", f"Total Rounds {k + 0.5:g}", "lines",
                                [sel("over", "Over", o, k + 0.5), sel("under", "Under", 1 - o, k + 0.5)], kind="2way"))
        return finalize(groups)

    @staticmethod
    def headline(groups: Sequence[Dict]) -> Dict:
        return TennisEngine.headline(groups)


# ============================================================================ Formula 1
class F1Engine:
    """Race outcome by Monte Carlo: utility = driver rating - grid penalty + Gumbel noise; DNF risk per driver."""

    def __init__(self, race_id: str, field: List[Dict], n_sim: int = 20000, grid_weight: float = 0.22,
                 noise: float = 1.0, model_label: str = "Rating + grid Monte Carlo", confidence: str = "ok"):
        self.field, self.n_sim, self.gw, self.noise = field, n_sim, grid_weight, noise
        self.seed = int(hashlib.md5(race_id.encode()).hexdigest()[:8], 16)
        self.model_label, self.confidence = model_label, confidence

    def simulate(self) -> Dict[str, np.ndarray]:
        rng = np.random.default_rng(self.seed)
        n = len(self.field)
        rating = np.array([float(d.get("rating", 0.0)) for d in self.field])
        grid = np.array([float(d.get("grid", i + 1)) for i, d in enumerate(self.field)])
        dnf = np.array([float(d.get("dnf", 0.08)) for d in self.field])
        u = rating[None, :] - self.gw * (grid[None, :] - 1) + rng.gumbel(0.0, self.noise, size=(self.n_sim, n))
        u = np.where(rng.random((self.n_sim, n)) < dnf[None, :], -1e9 + rng.random((self.n_sim, n)), u)
        order = np.argsort(-u, axis=1)
        pos = np.empty_like(order)
        rows = np.arange(self.n_sim)[:, None]
        pos[rows, order] = np.arange(n)[None, :]
        return {"pos": pos}

    def info(self, ev: Event) -> Dict:
        return {"model": self.model_label, "confidence": self.confidence}

    def markets(self, ev: Event) -> List[Dict]:
        pos = self.simulate()["pos"]
        names = [d["name"] for d in self.field]
        def top(k: int) -> np.ndarray:
            return (pos < k).mean(axis=0)
        win, pod, t6, pts = top(1), top(3), top(6), top(10)
        order = np.argsort(-win)[:12]
        groups = [group("winner", "Race Winner", "main", [sel(f"d{i}", names[i], win[i]) for i in order]),
                  group("podium", "Podium Finish (Top 3)", "main",
                        [sel(f"d{i}", names[i], pod[i]) for i in np.argsort(-pod)[:12]], kind="multi",
                        note="Each driver is an independent yes/no bet."),
                  group("top6", "Top 6 Finish", "lines", [sel(f"d{i}", names[i], t6[i]) for i in np.argsort(-t6)[:12]]),
                  group("points", "Points Finish (Top 10)", "lines",
                        [sel(f"d{i}", names[i], pts[i]) for i in np.argsort(-pts)[:14]])]
        return finalize(groups)

    @staticmethod
    def headline(groups: Sequence[Dict]) -> Dict:
        for g in groups:
            if g["id"] == "winner":
                return {"field": [{"label": s["label"], "prob": s["prob"]} for s in g["selections"][:3]]}
        return {}


# ============================================================================ Water Polo
class WaterpoloEngine:
    def __init__(self, home: str, away: str, lam: float = 11.2, mu: float = 9.6, alpha: float = 0.05,
                 model_label: str = "Waterpolo Poisson ratings", confidence: str = "ok"):
        self.home, self.away = home, away
        self.lam, self.mu, self.alpha = max(4.0, lam), max(4.0, mu), alpha
        self.model_label, self.confidence = model_label, confidence

    def _remaining(self, ev: Event) -> Tuple[float, float, bool]:
        if ev.status == "finished":
            return 0.0, 0.0, True
        if ev.status != "live":
            return self.lam, self.mu, False
        elapsed = float(ev.clock.get("elapsed", 0.0))
        rem = max(0.0, 1.0 - elapsed)
        return self.lam * rem, self.mu * rem, rem <= 1e-9

    def _dists(self, ev: Event) -> Tuple[ScoreDist, ScoreDist]:
        lr, mr, over = self._remaining(ev)
        h, a = ev.score
        reg = race_dist(lr, mr, h, a, self.alpha)
        fin = resolve_ties(reg, 0.52)
        return reg, fin

    def info(self, ev: Event) -> Dict:
        reg, fin = self._dists(ev)
        return {"expected_final": list(reg.expected()), "expected_total": float(sum(reg.expected())),
                "model": self.model_label, "confidence": self.confidence}

    def markets(self, ev: Event) -> List[Dict]:
        H, A = self.home, self.away
        reg, fin = self._dists(ev)
        groups: List[Dict] = []
        
        # 1X2 (32 min regulation)
        a_h, b_d, c_a = reg.p_1x2()
        groups.append(group("1x2", "Regulation Result (32')", "main",
                            [sel("home", H, a_h), sel("draw", "Draw", b_d), sel("away", A, c_a)], kind="3way"))

        # Moneyline (including Overtime / Penalty Shootout)
        ph = fin.p(fin.D > 0)
        groups.append(group("ml", "Match Winner (incl. OT/Pen)", "main",
                            [sel("home", H, ph), sel("away", A, 1.0 - ph)], kind="2way"))

        # Goal Handicap / Spreads
        for L in (-3.5, -2.5, -1.5, 1.5, 2.5, 3.5):
            pc = fin.p(fin.D + L > 0)
            if 0.02 <= pc <= 0.98:
                groups.append(group(f"sp_{L:+g}", f"Goal Handicap {_hl(L)}", "main" if abs(L) <= 1.5 else "lines",
                                    [sel("home", f"{H} {_hl(L)}", pc, L), sel("away", f"{A} {_hl(-L)}", 1.0 - pc, -L)], kind="2way"))

        # Total Goals
        mean_t = sum(reg.expected())
        T0 = nearest_half(mean_t)
        cur_t = ev.score[0] + ev.score[1]
        for k in range(-4, 5):
            T = T0 + k
            if T <= cur_t:
                continue
            o = reg.p(reg.T > T)
            if 0.02 <= o <= 0.98:
                groups.append(group(f"tot_{T:g}", f"Total Goals {T:g}", "main" if k == 0 else "lines",
                                    [sel("over", "Over", o, T), sel("under", "Under", 1.0 - o, T)], kind="2way"))

        # Team Totals
        for side, nm, arr in (("home", H, reg.X), ("away", A, reg.Y)):
            m = float((reg.G * arr).sum())
            T = nearest_half(m)
            o = reg.p(arr > T)
            groups.append(group(f"tt_{side}_{T:g}", f"{nm} Total Goals {T:g}", "specials",
                                [sel("over", "Over", o, T), sel("under", "Under", 1.0 - o, T)], kind="2way"))

        return finalize(groups)


# ============================================================================ settlement (2-way sports)
def settle_generic(gid: str, sid: str, final: Tuple[int, int], sport: str = "") -> Optional[str]:
    """Moneyline / spread / total / set settlement for the non-soccer engines."""
    h, a = final
    d, t = h - a, h + a
    win = lambda c: "won" if c else "lost"
    if gid == "1x2":
        if d > 0:
            return "won" if sid == "home" else "lost"
        elif d < 0:
            return "won" if sid == "away" else "lost"
        else:
            return "won" if sid == "draw" else "lost"
    if gid == "ml":
        if sport in ("tennis", "volleyball", "mma"):
            return win((h > a) == (sid == "a"))
        return win((d > 0) == (sid == "home")) if d != 0 else "void"
    for prefix in ("sp_", "pl_", "rl_", "sh_", "gl_"):
        if gid.startswith(prefix):
            L = float(gid[len(prefix):])
            m = d if sid in ("home", "a") else -d
            L = L if sid in ("home", "a") else -L
            return "void" if abs(m + L) < 1e-9 else win(m + L > 0)
    for prefix in ("tot_", "sets_", "pts_", "games_"):
        if gid.startswith(prefix):
            return win((t > float(gid[len(prefix):])) == (sid == "over"))
    return None
