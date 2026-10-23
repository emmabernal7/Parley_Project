"""Generic in-play maths for the non-soccer sports."""
from __future__ import annotations

import math
from typing import Dict, Tuple

import numpy as np

from ..markets.scoredist import ScoreDist
from ..mathutil import nb_pmf, norm_cdf


# ----------------------------------------------------------------------- Gaussian margin process
def gaussian_final(mean_margin: float, mean_total: float, sd_margin: float, sd_total: float,
                   elapsed: float, cur_margin: float, cur_total: float, ot_frac: float = 0.0) -> Dict[str, float]:
    """Distribution of the FINAL margin and total given the current score and the fraction played.

    The remaining margin is a Brownian motion with drift  mean_margin * (time left)  and variance
    sd_margin^2 * (time left): the classic "win probability from lead and time" model.
    """
    r = max(0.0, 1.0 - elapsed)
    if r <= 1e-9 and abs(cur_margin) < 1e-9 and ot_frac > 0:
        r = ot_frac                                   # level at the buzzer: overtime
    return {
        "mu_m": cur_margin + mean_margin * r, "sd_m": max(sd_margin * math.sqrt(r), 1e-6),
        "mu_t": cur_total + mean_total * r, "sd_t": max(sd_total * math.sqrt(r), 1e-6),
    }


def p_gt(x: float, mu: float, sd: float) -> float:
    """P(integer-valued score > x) for a normal approximation with continuity correction (works for
    half-lines and whole lines)."""
    k = math.floor(x) + 1
    return float(1.0 - norm_cdf((k - 0.5 - mu) / sd))


def p_ge(k: int, mu: float, sd: float) -> float:
    return float(1.0 - norm_cdf((k - 0.5 - mu) / sd))


# ----------------------------------------------------------------------- Poisson / NB race
def race_dist(lam_rem: float, mu_rem: float, h0: int, a0: int, alpha: float = 0.0, K: int = 30) -> ScoreDist:
    """Final-score distribution when the remaining goals / runs are independent counts."""
    G = np.outer(nb_pmf(lam_rem, alpha, K), nb_pmf(mu_rem, alpha, K))
    return ScoreDist(G, h0, a0)


def resolve_ties(dist: ScoreDist, p_home_extra: float = 0.5) -> ScoreDist:
    """Sports without draws (hockey with OT/SO, baseball with extra innings): a tied score is broken by
    one extra goal / run for the winner.  Returns the FINAL distribution including that extra score."""
    G = dist.G.copy()
    K1, K2 = G.shape
    big = np.zeros((K1 + 1, K2 + 1))
    big[:K1, :K2] = G
    for i in range(K1):
        for j in range(K2):
            if dist.X[i, j] == dist.Y[i, j]:
                q = G[i, j]
                big[i, j] -= q
                big[i + 1, j] += q * p_home_extra
                big[i, j + 1] += q * (1.0 - p_home_extra)
    return ScoreDist(big, dist.h0, dist.a0)
