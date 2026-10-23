"""Soccer pricer: model rates + match state  ->  every market, before and during the match."""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..events import Event
from ..inplay.soccer import (InPlayParams, SoccerState, calibrate_scale, first_half_dist, half_weights,
                             inplay_dist, lead_hit_prob, make_tilt, next_goal_probs, window_goal_probs)
from ..markets.schema import finalize, group, sel
from ..markets.scoredist import ScoreDist
from ..mathutil import pois_pmf
from ..models.dixon_coles import dc_grid


def fmt_line(x: float) -> str:
    return "0" if abs(x) < 1e-9 else f"{x:+g}"


def htft_table(lam1: float, mu1: float, lam2: float, mu2: float, kmax: int = 8):
    """Joint half-time / full-time result from two independent halves (Poisson each)."""
    def diff(p):
        d: Dict[int, float] = {}
        for i in range(p.shape[0]):
            for j in range(p.shape[1]):
                d[i - j] = d.get(i - j, 0.0) + p[i, j]
        return d
    p1 = np.outer(pois_pmf(lam1, kmax), pois_pmf(mu1, kmax))
    p2 = np.outer(pois_pmf(lam2, kmax), pois_pmf(mu2, kmax))
    d1, d2 = diff(p1), diff(p2)
    cls = lambda v: "H" if v > 0 else ("D" if v == 0 else "A")
    out = {(a, b): 0.0 for a in "HDA" for b in "HDA"}
    for x, px in d1.items():
        for y, py in d2.items():
            out[(cls(x), cls(x + y))] += px * py
    tot = sum(out.values())
    return {k: v / tot for k, v in out.items()}


def state_from_event(ev: Event) -> SoccerState:
    """Translate the generic Event into the soccer in-play state."""
    if ev.status == "finished":
        phase = "ft"
    elif ev.status == "live":
        phase = ev.clock.get("phase", "h1")
    else:
        phase = "pre"
    if phase not in ("pre", "h1", "ht", "h2", "ft"):
        phase = "ft"    # extra time / penalties: the 90-minute markets are already settled
    return SoccerState(
        phase=phase, minute=float(ev.clock.get("minute", 0.0) or 0.0), home=int(ev.score[0]), away=int(ev.score[1]),
        red_home=int(ev.live.get("red_home", 0)), red_away=int(ev.live.get("red_away", 0)),
        goals=list(ev.live.get("goals", [])),
    )


class SoccerPricer:
    def __init__(self, home: str, away: str, lam: float, mu: float, rho: float = -0.05,
                 params: Optional[InPlayParams] = None, cards: Optional[Dict] = None,
                 corners: Optional[Dict] = None, model_label: str = "Dixon-Coles",
                 confidence: str = "ok"):
        self.home, self.away = home, away
        self.lam, self.mu, self.rho = float(lam), float(mu), float(rho)
        self.p = params or InPlayParams()
        self._scale: Optional[Tuple[float, float]] = None
        self._tilt: Optional[np.ndarray] = None
        self.g_pre = dc_grid(self.lam, self.mu, self.rho, 10)
        self.cards, self.corners = cards, corners
        self.model_label, self.confidence = model_label, confidence

    @property
    def scale(self) -> Tuple[float, float]:
        if self._scale is None:
            self._scale = calibrate_scale(self.lam, self.mu, self.p)
        return self._scale

    @property
    def tilt(self) -> np.ndarray:
        if self._tilt is None:
            self._tilt = make_tilt(self.lam, self.mu, self.rho, self.p, self.scale)
        return self._tilt

    # ------------------------------------------------------------------ distributions
    def dist(self, st: SoccerState) -> ScoreDist:
        if st.phase == "pre":
            return ScoreDist(self.g_pre)
        return inplay_dist(self.lam, self.mu, st, self.p, self.scale, self.tilt)

    def info(self, st: SoccerState) -> Dict:
        d = self.dist(st)
        eh, ea = d.expected()
        return {"lam": self.lam, "mu": self.mu, "expected_final": [eh, ea], "model": self.model_label,
                "confidence": self.confidence}

    def main_market(self, st: SoccerState) -> Dict:
        H, A = self.home, self.away
        d = self.dist(st)
        ph, pdw, pa = d.p_1x2()
        g = group("1x2", "1x2", "main",
                  [sel("home", H, ph), sel("draw", "Empate", pdw), sel("away", A, pa)], kind="3way")
        return finalize([g])[0]

    # ------------------------------------------------------------------ markets
    def markets(self, st: SoccerState) -> List[Dict]:
        H, A = self.home, self.away
        d = self.dist(st)
        cur_h, cur_a = st.home, st.away
        cur_t = cur_h + cur_a
        pre = st.phase == "pre"
        active = st.phase in ("pre", "h1", "ht", "h2")
        groups: List[Dict] = []

        ph, pdw, pa = d.p_1x2()
        groups.append(group("1x2", "1x2", "main",
                            [sel("home", H, ph), sel("draw", "Empate", pdw), sel("away", A, pa)], kind="3way"))

        # ---- 1UP / 2UP : pays as a win when the team leads by 1 / 2 goals at any time
        if active:
            for tgt, gid in ((1, "1up"), (2, "2up")):
                up_h = lead_hit_prob(self.lam, self.mu, st, self.p, self.scale, tgt, "home")
                up_a = lead_hit_prob(self.lam, self.mu, st, self.p, self.scale, tgt, "away")
                groups.append(group(gid, f"1x2 ({tgt}UP) - Paid at {tgt} Goal Lead", "main",
                                    [sel("home", H, up_h), sel("draw", "Empate", pdw), sel("away", A, up_a)],
                                    kind="3way", note=f"Home / Away pay out as a win as soon as that team leads by {tgt}."))
        dc = d.p_double_chance()
        groups.append(group("dc", "Double Chance", "main",
                            [sel("1x", f"{H} o Empate", dc["1x"]), sel("12", f"{H} o {A}", dc["12"]),
                             sel("x2", f"Empate o {A}", dc["x2"])], kind="3way"))
        dh, da = d.p_dnb()
        groups.append(group("dnb", "Draw No Bet", "main", [sel("home", H, dh), sel("away", A, da)], kind="2way",
                            note="Stake is returned if the match ends level."))
        b = d.p_btts()
        groups.append(group("btts", "Both Teams to Score", "main", [sel("yes", "Sí", b), sel("no", "No", 1 - b)], kind="2way"))

        # ---- totals
        cand = [l for l in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5) if l > cur_t]
        main_line = None
        if cand:
            main_line = min(cand, key=lambda l: abs(d.p_over(l)[0] - 0.5))
            o, _, u = d.p_over(main_line)
            groups.append(group(f"ou_{main_line:g}", f"Total Goals {main_line:g}", "main",
                                [sel("over", "Over", o, main_line), sel("under", "Under", u, main_line)], kind="2way"))
        for l in cand:
            o, _, u = d.p_over(l)
            groups.append(group(f"ou_{l:g}", f"Total Goals {l:g}", "goals",
                                [sel("over", "Over", o, l), sel("under", "Under", u, l)], kind="2way"))
        for side, nm, cur in (("home", H, cur_h), ("away", A, cur_a)):
            for l in (0.5, 1.5, 2.5, 3.5):
                if l > cur:
                    o, u = d.p_team_over(side, l)
                    groups.append(group(f"tt_{side}_{l:g}", f"{nm} Total Goals {l:g}", "goals",
                                        [sel("over", "Over", o, l), sel("under", "Under", u, l)], kind="2way"))
        ex = [sel(str(n), str(n), d.p_exact_total(n)) for n in range(cur_t, cur_t + 6)]
        ex.append(sel(f"{cur_t + 6}+", f"{cur_t + 6}+", d.p_exact_total(cur_t + 6, or_more=True)))
        groups.append(group("exact_goals", "Exact Total Goals", "goals", ex))
        odd = d.p_odd_total()
        groups.append(group("odd_even", "Total Goals Odd / Even", "goals",
                            [sel("odd", "Odd", odd), sel("even", "Even", 1 - odd)], kind="2way"))

        # ---- Asian lines
        for L in np.arange(-2.5, 2.501, 0.25):
            sh, sa = d.asian_handicap(float(L), "home"), d.asian_handicap(float(-L), "away")
            if sh.W + sh.L <= 0 or max(sh.prob_adj, sa.prob_adj) > 0.965:
                continue
            groups.append(group(f"ah_{L:+.2f}", f"Asian Handicap {fmt_line(float(L))}", "asian", [
                sel("home", f"{H} {fmt_line(float(L))}", sh.prob_adj, float(L),
                    outcomes={"win": sh.win, "half_win": sh.half_win, "push": sh.push, "half_loss": sh.half_loss, "loss": sh.loss}),
                sel("away", f"{A} {fmt_line(float(-L))}", sa.prob_adj, float(-L),
                    outcomes={"win": sa.win, "half_win": sa.half_win, "push": sa.push, "half_loss": sa.half_loss, "loss": sa.loss}),
            ], kind="2way", note="Push-adjusted probability; quarter lines split the stake."))
        for L in np.arange(0.75, 5.01, 0.25):
            if abs(L * 2 - round(L * 2)) < 1e-9 and abs(L - round(L)) > 1e-9:
                continue    # plain half lines already live in the goals tab
            if L <= cur_t - 0.25:
                continue
            so, su = d.asian_total(float(L), "over"), d.asian_total(float(L), "under")
            if so.W + so.L <= 0 or max(so.prob_adj, su.prob_adj) > 0.965:
                continue
            groups.append(group(f"at_{L:g}", f"Asian Total Goals {L:g}", "asian",
                                [sel("over", "Over", so.prob_adj, float(L)), sel("under", "Under", su.prob_adj, float(L))],
                                kind="2way"))

        # ---- halves
        l1, l2 = self.p.h1_share, 1.0 - self.p.h1_share
        if st.phase in ("pre", "h1"):
            if pre:
                dht = ScoreDist(np.outer(pois_pmf(self.lam * l1, 10), pois_pmf(self.mu * l1, 10)))
            else:
                dht = first_half_dist(self.lam, self.mu, st, self.p, self.scale)
            hh, hd, ha = dht.p_1x2()
            groups.append(group("ht_1x2", "Half Time Result", "half",
                                [sel("home", H, hh), sel("draw", "Draw", hd), sel("away", A, ha)], kind="3way"))
            cur_ht = st.home + st.away
            for l in (0.5, 1.5, 2.5):
                if l > cur_ht:
                    o, _, u = dht.p_over(l)
                    groups.append(group(f"h1_ou_{l:g}", f"1st Half Total Goals {l:g}", "half",
                                        [sel("over", "Over", o, l), sel("under", "Under", u, l)], kind="2way"))
        if pre:
            for l in (0.5, 1.5, 2.5):
                p2 = ScoreDist(np.outer(pois_pmf(self.lam * l2, 10), pois_pmf(self.mu * l2, 10)))
                o, _, u = p2.p_over(l)
                groups.append(group(f"h2_ou_{l:g}", f"2nd Half Total Goals {l:g}", "half",
                                    [sel("over", "Over", o, l), sel("under", "Under", u, l)], kind="2way"))
            tab = htft_table(self.lam * l1, self.mu * l1, self.lam * l2, self.mu * l2)
            name = {"H": H, "D": "Draw", "A": A}
            groups.append(group("htft", "Half Time / Full Time", "half",
                                [sel(f"{a}{b}", f"{name[a]} / {name[b]}", tab[(a, b)]) for a in "HDA" for b in "HDA"],
                                note="Approximation: the two halves are treated as independent."))
            p1 = pois_pmf((self.lam + self.mu) * l1, 14)
            p2 = pois_pmf((self.lam + self.mu) * l2, 14)
            first = sum(p1[i] * p2[:i].sum() for i in range(15))
            second = sum(p2[i] * p1[:i].sum() for i in range(15))
            groups.append(group("high_half", "Highest Scoring Half", "half",
                                [sel("first", "1st half", first), sel("equal", "Equal", max(0.0, 1 - first - second)),
                                 sel("second", "2nd half", second)], kind="3way"))

        # ---- specials
        cs = d.correct_scores(12)
        rest = max(0.0, 1.0 - sum(p for _, p in cs))
        groups.append(group("cs", "Correct Score", "specials",
                            [sel(lbl, lbl, p) for lbl, p in cs] + [sel("other", "Any other score", rest)]))
        wm = d.winning_margin()
        groups.append(group("margin", "Winning Margin", "specials", [
            sel("home_3plus", f"{H} by 3+", wm["home_3plus"]), sel("home_2", f"{H} by 2", wm["home_2"]),
            sel("home_1", f"{H} by 1", wm["home_1"]), sel("draw", "Draw", wm["draw"]),
            sel("away_1", f"{A} by 1", wm["away_1"]), sel("away_2", f"{A} by 2", wm["away_2"]),
            sel("away_3plus", f"{A} by 3+", wm["away_3plus"])]))
        cs_h, cs_a = d.p_clean_sheet("home"), d.p_clean_sheet("away")
        groups.append(group("cs_home", f"{H} Clean Sheet", "specials", [sel("yes", "Yes", cs_h), sel("no", "No", 1 - cs_h)], kind="2way"))
        groups.append(group("cs_away", f"{A} Clean Sheet", "specials", [sel("yes", "Yes", cs_a), sel("no", "No", 1 - cs_a)], kind="2way"))
        groups.append(group("wtn", "Win to Nil", "specials", [sel("home", H, d.p_win_to_nil("home")),
                                                              sel("away", A, d.p_win_to_nil("away"))]))
        if active:
            ng = next_goal_probs(self.lam, self.mu, st, self.p, self.scale)
            gid, name = ("first_goal", "First Goal") if (pre or cur_t == 0) else ("next_goal", "Next Goal")
            groups.append(group(gid, name, "specials", [sel("home", H, ng["home"]), sel("none", "No goal", ng["none"]),
                                                        sel("away", A, ng["away"])], kind="3way"))

        # ---- minute markets
        if active:
            L1, L2 = 45 + self.p.stoppage1, 45 + self.p.stoppage2
            wins = [("0-15", 0, 15), ("15-30", 15, 30), (f"30-45+", 30, L1), ("45-60", L1, L1 + 15),
                    ("60-75", L1 + 15, L1 + 30), ("75-90+", L1 + 30, L1 + L2)]
            wp = window_goal_probs(self.lam, self.mu, st, self.p, self.scale, wins)
            for label, prob in wp.items():
                groups.append(group(f"min_{label}", f"Goal between minutes {label}", "minute",
                                    [sel("yes", "Yes", prob), sel("no", "No", 1 - prob)], kind="2way"))

        # ---- cards and corners (pre-match model, needs history with referees / corners)
        if pre:
            if self.cards:
                groups.extend(self._count_groups("cards", "Cards", self.cards, (2.5, 3.5, 4.5, 5.5, 6.5), (0.5, 1.5, 2.5)))
            if self.corners:
                groups.extend(self._count_groups("corners", "Corners", self.corners, (7.5, 8.5, 9.5, 10.5, 11.5, 12.5), (3.5, 4.5, 5.5)))

        # ---- same-game combos
        if active and cur_t == 0:
            groups.extend(self._sgm(d))
        return finalize(groups)

    # ------------------------------------------------------------------ helpers
    def _count_groups(self, key: str, title: str, m: Dict, tot_lines, team_lines) -> List[Dict]:
        out = []
        note = None
        if key == "cards" and m.get("referee"):
            note = f"Referee: {m['referee']} (x{m.get('ref_mult', 1.0):.2f} vs an average referee)"
        over = lambda pmf, L: float(pmf[int(L) + 1:].sum())
        for L in tot_lines:
            o = over(m["total"], L)
            out.append(group(f"{key}_{L:g}", f"Total {title} {L:g}", "specials",
                             [sel("over", "Over", o, L), sel("under", "Under", 1 - o, L)], kind="2way", note=note))
        for side, nm in (("home", self.home), ("away", self.away)):
            for L in team_lines:
                o = over(m[side], L)
                out.append(group(f"{key}_{side}_{L:g}", f"{nm} {title} {L:g}", "specials",
                                 [sel("over", "Over", o, L), sel("under", "Under", 1 - o, L)], kind="2way", note=note))
        return out

    def _sgm(self, d: ScoreDist) -> List[Dict]:
        H, A = self.home, self.away
        T = lambda l, s: {"market": "total", "line": l, "selection": s}
        R = lambda s: {"market": "1x2", "selection": s}
        B = lambda s: {"market": "btts", "selection": s}
        DCx = lambda s: {"market": "double_chance", "selection": s}
        combos = [
            (f"{H} to win & Over 2.5", [R("home"), T(2.5, "over")]),
            (f"{H} to win & Under 3.5", [R("home"), T(3.5, "under")]),
            (f"{H} to win & Both teams score", [R("home"), B("yes")]),
            (f"{H} to win & Over 1.5", [R("home"), T(1.5, "over")]),
            (f"{A} to win & Over 2.5", [R("away"), T(2.5, "over")]),
            (f"{A} to win & Both teams score", [R("away"), B("yes")]),
            (f"{A} to win & Under 3.5", [R("away"), T(3.5, "under")]),
            ("Draw & Under 2.5", [R("draw"), T(2.5, "under")]),
            ("Draw & Both teams score", [R("draw"), B("yes")]),
            ("Both teams score & Over 2.5", [B("yes"), T(2.5, "over")]),
            ("Both teams score & Over 3.5", [B("yes"), T(3.5, "over")]),
            ("Both teams NOT score & Under 2.5", [B("no"), T(2.5, "under")]),
            (f"{H} or Draw & Under 3.5", [DCx("1x"), T(3.5, "under")]),
            (f"{A} or Draw & Over 1.5", [DCx("x2"), T(1.5, "over")]),
        ]
        sels = []
        for i, (label, legs) in enumerate(combos):
            joint = d.joint(legs)
            naive = float(np.prod([d.joint([lg]) for lg in legs]))
            sels.append(sel(f"c{i}", label, joint, naive=naive, corr=(joint / naive if naive > 0 else 1.0)))
        return [group("sgm", "Same Game Multi", "sgm", sels,
                      note="Joint probabilities computed exactly on the scoreline table (legs are correlated).")]

    # ------------------------------------------------------------------ headline
    @staticmethod
    def headline(groups: Sequence[Dict]) -> Dict:
        out: Dict = {}
        for g in groups:
            if g["id"] == "1x2":
                out["1x2"] = {s["id"]: s["prob"] for s in g["selections"]}
            if g["id"].startswith("ou_") and g["tab"] == "main":
                out["total"] = {"line": g["selections"][0].get("line"), "over": g["selections"][0]["prob"],
                                "under": g["selections"][1]["prob"]}
            if g["id"] == "btts":
                out["btts"] = g["selections"][0]["prob"]
        return out


# ---------------------------------------------------------------------- settlement
def settle_soccer(gid: str, sid: str, final: Tuple[int, int], ht: Optional[Tuple[int, int]] = None,
                  goals: Optional[Sequence[str]] = None, stats: Optional[Dict] = None,
                  line: Optional[float] = None) -> Optional[str]:
    """Result of a selection given the final score: won | lost | void | half_won | half_lost | None (unknown)."""
    h, a = final
    d, t = h - a, h + a
    win = lambda c: "won" if c else "lost"

    def asian(margin: float, ln: float) -> str:
        from ..markets.scoredist import split_line
        subs = split_line(ln)
        w = sum(1 for s in subs if margin + s > 1e-9)
        l = sum(1 for s in subs if margin + s < -1e-9)
        if w == len(subs):
            return "won"
        if l == len(subs):
            return "lost"
        if w == 0 and l == 0:
            return "void"
        return "half_won" if w > 0 else "half_lost"

    if gid == "1x2":
        return win({"home": d > 0, "draw": d == 0, "away": d < 0}[sid])
    if gid in ("1up", "2up"):
        tgt = 1 if gid == "1up" else 2
        if sid == "draw":
            return win(d == 0)
        seq = list(goals or [])
        run = mx_h = mx_a = 0
        for g in seq:
            run += 1 if g == "h" else -1
            mx_h, mx_a = max(mx_h, run), max(mx_a, -run)
        if not seq:
            mx_h, mx_a = max(d, 0), max(-d, 0)
        return win((mx_h if sid == "home" else mx_a) >= tgt or (d > 0 if sid == "home" else d < 0))
    if gid == "dc":
        return win({"1x": d >= 0, "12": d != 0, "x2": d <= 0}[sid])
    if gid == "dnb":
        return "void" if d == 0 else win((d > 0) == (sid == "home"))
    if gid == "btts":
        return win((h > 0 and a > 0) == (sid == "yes"))
    if gid.startswith("ou_"):
        ln = float(gid[3:])
        return win((t > ln) == (sid == "over"))
    if gid.startswith("tt_"):
        _, side, ln = gid.split("_")
        n = h if side == "home" else a
        return win((n > float(ln)) == (sid == "over"))
    if gid == "exact_goals":
        return win(sid == f"{t}" or (sid.endswith("+") and t >= int(sid[:-1])))
    if gid == "odd_even":
        return win((t % 2 == 1) == (sid == "odd"))
    if gid.startswith("ah_"):
        ln = float(gid[3:])
        return asian((d if sid == "home" else -d) * 1.0, ln if sid == "home" else -ln)
    if gid.startswith("at_"):
        ln = float(gid[3:])
        return asian(t - 0.0, -ln) if sid == "over" else asian(-t, ln)
    if gid == "cs":
        if sid == "other":
            return None
        return win(sid == f"{h}-{a}")
    if gid == "margin":
        return win({"home_3plus": d >= 3, "home_2": d == 2, "home_1": d == 1, "draw": d == 0,
                    "away_1": d == -1, "away_2": d == -2, "away_3plus": d <= -3}[sid])
    if gid == "cs_home":
        return win((a == 0) == (sid == "yes"))
    if gid == "cs_away":
        return win((h == 0) == (sid == "yes"))
    if gid == "wtn":
        return win((d > 0 and a == 0) if sid == "home" else (d < 0 and h == 0))
    if gid in ("first_goal", "next_goal"):
        seq = list(goals or [])
        if not seq:
            return win(sid == "none") if t == 0 else None
        return win(sid == ("home" if seq[0] == "h" else "away"))
    if gid == "ht_1x2" and ht is not None:
        dh = ht[0] - ht[1]
        return win({"home": dh > 0, "draw": dh == 0, "away": dh < 0}[sid])
    if gid.startswith("h1_ou_") and ht is not None:
        return win((ht[0] + ht[1] > float(gid[6:])) == (sid == "over"))
    if gid.startswith("h2_ou_") and ht is not None:
        return win((t - ht[0] - ht[1] > float(gid[6:])) == (sid == "over"))
    if gid == "htft" and ht is not None:
        c = lambda v: "H" if v > 0 else ("D" if v == 0 else "A")
        return win(sid == f"{c(ht[0] - ht[1])}{c(d)}")
    if gid.startswith("min_") or gid == "sgm" or gid.startswith(("cards", "corners")):
        return None
    return None
