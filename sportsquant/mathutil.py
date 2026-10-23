"""Small numerical helpers shared by every model."""
from __future__ import annotations

import math

import numpy as np
from scipy.special import gammaln, ndtr


def pois_pmf(lam: float, kmax: int) -> np.ndarray:
    """P(N = k) for k = 0..kmax, N ~ Poisson(lam).  Safe for lam = 0."""
    k = np.arange(kmax + 1)
    if lam <= 0.0:
        out = np.zeros(kmax + 1)
        out[0] = 1.0
        return out
    return np.exp(-lam + k * math.log(lam) - gammaln(k + 1))


def nb_pmf(mean: float, alpha: float, kmax: int) -> np.ndarray:
    """Negative binomial with mean `mean` and variance mean * (1 + alpha * mean).

    alpha -> 0 recovers the Poisson.  Used for corners / cards / baseball runs, which are
    more spread out than a Poisson count.
    """
    if alpha < 1e-6 or mean <= 0.0:
        return pois_pmf(mean, kmax)
    r = 1.0 / alpha
    k = np.arange(kmax + 1)
    logp = (gammaln(k + r) - gammaln(r) - gammaln(k + 1)
            + r * math.log(r / (r + mean)) + k * math.log(mean / (r + mean)))
    return np.exp(logp)


def norm_cdf(x):
    """Standard normal cdf (vectorised)."""
    return ndtr(x)


def clip01(p: float, eps: float = 1e-9) -> float:
    return float(min(1.0 - eps, max(eps, p)))
