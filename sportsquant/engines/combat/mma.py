"""Combat pricing engine for Mixed Martial Arts (MMA)."""
from __future__ import annotations

from typing import Dict, List, Sequence

from ...events import Event
from ...markets.schema import finalize, group, sel
from ..court.tennis import TennisEngine


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
