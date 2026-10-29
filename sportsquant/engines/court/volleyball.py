"""Rally Markov chain pricing engine for Volleyball."""
from __future__ import annotations

from typing import Dict, List, Sequence

from ...events import Event
from ...markets.schema import finalize, group, sel
from ...models.racket import rally_prob_for_win, volleyball_match
from ..common import _hl, nearest_half
from .tennis import TennisEngine


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
