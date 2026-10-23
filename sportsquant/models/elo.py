"""Elo ratings and the Elo -> goals bridge used for matches between teams of different leagues."""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from ..mathutil import pois_pmf


def elo_expected(diff: float) -> float:
    """Expected score of the side rated `diff` points higher (win = 1, draw = 0.5)."""
    return 1.0 / (1.0 + 10.0 ** (-diff / 400.0))


class EloBook:
    """A table of Elo ratings that can be fitted from results and updated one result at a time."""

    def __init__(self, k: float = 24.0, base: float = 1500.0):
        self.k, self.base = k, base
        self.r: Dict[str, float] = {}

    def get(self, name: str) -> float:
        return self.r.get(name, self.base)

    def expected(self, a: str, b: str, hfa: float = 0.0) -> float:
        return elo_expected(self.get(a) + hfa - self.get(b))

    def update(self, a: str, b: str, score_a: float, hfa: float = 0.0) -> None:
        ea = self.expected(a, b, hfa)
        delta = self.k * (score_a - ea)
        self.r[a] = self.get(a) + delta
        self.r[b] = self.get(b) - delta

    def fit(self, df: pd.DataFrame, a_col: str = "home", b_col: str = "away", score_col: str = "score_a",
            hfa: float = 0.0) -> "EloBook":
        """df sorted by date; score_a = 1 if A won, 0.5 draw, 0 loss."""
        for a, b, s in zip(df[a_col], df[b_col], df[score_col]):
            self.update(a, b, float(s), hfa)
        return self


def _expected_score_poisson(D: float, T: float, K: int = 14) -> float:
    lam, mu = (T + D) / 2.0, (T - D) / 2.0
    g = np.outer(pois_pmf(lam, K), pois_pmf(mu, K))
    g /= g.sum()
    return float(np.tril(g, -1).sum() + 0.5 * np.trace(g))


def elo_to_goal_rates(delta: float, total: float = 2.7) -> Tuple[float, float]:
    """Expected goals (home, away) so that the match's Elo expected score equals that of the goal model.

    delta = Elo(home) + home advantage - Elo(away).  Solved numerically: find the expected goal
    difference D with  P(win) + P(draw)/2 [Poisson goals]  =  1 / (1 + 10^(-delta/400)).
    """
    target = elo_expected(delta)
    lim = total - 0.15
    D = brentq(lambda d: _expected_score_poisson(d, total) - target, -lim, lim)
    return (total + D) / 2.0, (total - D) / 2.0
