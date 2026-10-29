"""Markov chain pricing engine for Tennis."""
from __future__ import annotations

from typing import Dict, List, Sequence

from ...events import Event
from ...markets.schema import finalize, group, sel
from ...models.racket import serve_probs_for_win, set_dist, tennis_match
from ..common import _hl, nearest_half


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
