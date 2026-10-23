"""ScoreDist: the probability distribution of the FINAL score of a two-team match.

Everything a bookmaker sells on the final result (1x2, totals, handicaps, both teams to score,
correct score...) is just a sum of probabilities over cells of this table.  Before kickoff the
table comes from the Dixon-Coles model; during the match it is recomputed from the current score
and the time left, so the prices "move" after every goal.

    G[i, j] = P(final score is (h0 + i, a0 + j))      (h0, a0 = goals already scored)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np


@dataclass
class Settled:
    """Outcome fractions of a (possibly Asian / quarter-line) bet, from the bettor's side."""
    win: float          # P(full win)
    half_win: float
    push: float
    half_loss: float
    loss: float
    W: float            # expected winning fraction of the stake
    L: float            # expected losing fraction of the stake

    @property
    def prob_adj(self) -> float:
        """Push-adjusted win probability W / (W + L).  Fair decimal odds = 1 / prob_adj."""
        d = self.W + self.L
        return self.W / d if d > 0 else 0.0

    def fair_odds(self) -> float:
        return 1.0 + self.L / self.W if self.W > 0 else 1000.0

    def ev(self, odds: float) -> float:
        return self.W * (odds - 1.0) - self.L


def split_line(line: float) -> List[float]:
    """Quarter lines (x.25 / x.75) are two half-stakes on the neighbouring half / whole lines."""
    twice = round(line * 2.0, 9)
    if abs(twice - round(twice)) < 1e-9:
        return [float(line)]
    return [line - 0.25, line + 0.25]


def _settle(prob: np.ndarray, margin: np.ndarray, sub_lines: Sequence[float]) -> Settled:
    """margin + s > 0 wins, == 0 pushes, < 0 loses, for each sub-line s (equal stake split)."""
    n = len(sub_lines)
    w = np.zeros_like(margin, dtype=float)
    l = np.zeros_like(margin, dtype=float)
    for s in sub_lines:
        r = margin + s
        w += (r > 1e-9)
        l += (r < -1e-9)
    w /= n
    l /= n
    return Settled(
        win=float(prob[(w == 1.0)].sum()),
        half_win=float(prob[(w == 0.5) & (l == 0.0)].sum()),
        push=float(prob[(w == 0.0) & (l == 0.0)].sum()),
        half_loss=float(prob[(l == 0.5) & (w == 0.0)].sum()),
        loss=float(prob[(l == 1.0)].sum()),
        W=float((prob * w).sum()),
        L=float((prob * l).sum()),
    )


class ScoreDist:
    def __init__(self, G: np.ndarray, h0: int = 0, a0: int = 0):
        G = np.asarray(G, dtype=float)
        self.G = G / G.sum()
        self.h0, self.a0 = int(h0), int(a0)
        K1, K2 = self.G.shape
        self.X = (self.h0 + np.arange(K1))[:, None] * np.ones((1, K2), dtype=int)
        self.Y = (self.a0 + np.arange(K2))[None, :] * np.ones((K1, 1), dtype=int)
        self.T = self.X + self.Y
        self.D = self.X - self.Y

    # ------------------------------------------------------------ primitives
    def p(self, mask: np.ndarray) -> float:
        return float(self.G[mask].sum())

    def expected(self) -> Tuple[float, float]:
        return float((self.G * self.X).sum()), float((self.G * self.Y).sum())

    # ------------------------------------------------------------ result markets
    def p_1x2(self) -> Tuple[float, float, float]:
        return self.p(self.D > 0), self.p(self.D == 0), self.p(self.D < 0)

    def p_double_chance(self) -> Dict[str, float]:
        ph, pd_, pa = self.p_1x2()
        return {"1x": ph + pd_, "12": ph + pa, "x2": pd_ + pa}

    def p_dnb(self) -> Tuple[float, float]:
        """Draw no bet: probabilities excluding the draw (fair odds = 1/p)."""
        ph, pd_, pa = self.p_1x2()
        s = ph + pa
        return (ph / s, pa / s) if s > 0 else (0.5, 0.5)

    # ------------------------------------------------------------ goals markets
    def p_over(self, line: float) -> Tuple[float, float, float]:
        """(over, push, under) for a total-goals line."""
        return self.p(self.T > line), self.p(self.T == line), self.p(self.T < line)

    def p_team_over(self, side: str, line: float) -> Tuple[float, float]:
        arr = self.X if side == "home" else self.Y
        return self.p(arr > line), self.p(arr < line)

    def p_btts(self) -> float:
        return self.p((self.X > 0) & (self.Y > 0))

    def p_exact_total(self, n: int, or_more: bool = False) -> float:
        return self.p(self.T >= n) if or_more else self.p(self.T == n)

    def p_odd_total(self) -> float:
        return self.p(self.T % 2 == 1)

    def p_clean_sheet(self, side: str) -> float:
        """P(the given side concedes nothing)."""
        return self.p(self.Y == 0) if side == "home" else self.p(self.X == 0)

    def p_win_to_nil(self, side: str) -> float:
        return self.p((self.D > 0) & (self.Y == 0)) if side == "home" else self.p((self.D < 0) & (self.X == 0))

    def winning_margin(self) -> Dict[str, float]:
        return {
            "home_3plus": self.p(self.D >= 3), "home_2": self.p(self.D == 2), "home_1": self.p(self.D == 1),
            "draw": self.p(self.D == 0),
            "away_1": self.p(self.D == -1), "away_2": self.p(self.D == -2), "away_3plus": self.p(self.D <= -3),
        }

    def correct_scores(self, top: int = 12) -> List[Tuple[str, float]]:
        cells = [(f"{x}-{y}", float(self.G[i, j]))
                 for i, x in enumerate(range(self.h0, self.h0 + self.G.shape[0]))
                 for j, y in enumerate(range(self.a0, self.a0 + self.G.shape[1]))]
        cells.sort(key=lambda t: -t[1])
        return cells[:top]

    # ------------------------------------------------------------ Asian lines
    def asian_handicap(self, line: float, side: str = "home") -> Settled:
        """Asian handicap.  `line` is the handicap given to `side` (home -0.75 = home gives 0.75 goals)."""
        margin = (self.D if side == "home" else -self.D).astype(float)
        return _settle(self.G, margin, split_line(line))

    def asian_total(self, line: float, side: str = "over") -> Settled:
        tot = self.T.astype(float)
        if side == "over":
            return _settle(self.G, tot, [-s for s in split_line(line)])
        return _settle(self.G, -tot, split_line(line))

    # ------------------------------------------------------------ joint (same-game) probabilities
    def leg_mask(self, leg: Dict) -> np.ndarray:
        """Boolean mask of the score cells where a leg wins.  Only half-lines (x.5) are supported
        for totals, so every leg is a clean yes/no event and can be combined exactly."""
        m = str(leg.get("market", "")).lower()
        sel = str(leg.get("selection", "")).lower()
        if m in ("1x2", "match_result", "result"):
            return {"home": self.D > 0, "1": self.D > 0, "draw": self.D == 0, "x": self.D == 0,
                    "away": self.D < 0, "2": self.D < 0}[sel]
        if m in ("double_chance", "dc"):
            return {"1x": self.D >= 0, "12": self.D != 0, "x2": self.D <= 0}[sel]
        if m in ("total", "totals", "ou", "over_under"):
            line = float(leg["line"])
            if abs(line * 2 - round(line * 2)) > 1e-9 or abs(line - round(line)) < 1e-9:
                raise ValueError("Same-game legs need half lines such as 1.5 / 2.5 / 3.5")
            return self.T > line if sel == "over" else self.T < line
        if m == "btts":
            yes = (self.X > 0) & (self.Y > 0)
            return yes if sel in ("yes", "y") else ~yes
        if m in ("team_total", "tt"):
            arr = self.X if str(leg.get("team", "home")).lower() == "home" else self.Y
            line = float(leg["line"])
            return arr > line if sel == "over" else arr < line
        if m == "correct_score":
            x, y = sel.split("-")
            return (self.X == int(x)) & (self.Y == int(y))
        raise ValueError(f"unsupported leg: {leg}")

    def joint(self, legs: Sequence[Dict]) -> float:
        mask = np.ones_like(self.G, dtype=bool)
        for leg in legs:
            mask &= self.leg_mask(leg)
        return self.p(mask)
