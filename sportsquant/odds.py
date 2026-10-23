"""Odds arithmetic.

Vocabulary (the thing you could not remember is called DECIMAL ODDS, also "European odds"):

    decimal odds 1.67   -> a stake of 1.00 returns 1.67 in total (0.67 profit)
    probability  59.9 % -> the same statement seen as a chance: p = 1 / odds

So "Barcelona 1.28" and "78.1 %" say the same thing.  A bookmaker's numbers add up to MORE
than 100 % (the overround, or "vig"): that excess is the bookmaker's built-in profit.
Fair odds (what this program shows) have no margin: 1 / p exactly.
"""
from __future__ import annotations

import math
import re
from typing import Optional, Sequence

import numpy as np
from scipy.optimize import brentq

MIN_ODDS = 1.01
MAX_ODDS = 1000.0


# ---------------------------------------------------------------- conversions
def prob_to_odds(p: float, floor: float = MIN_ODDS, cap: float = MAX_ODDS) -> float:
    """Fair decimal odds for probability p, clipped to a displayable range."""
    if p is None or not math.isfinite(p) or p <= 0.0:
        return cap
    return float(min(cap, max(floor, 1.0 / p)))


def odds_to_prob(odds: float) -> float:
    """Implied probability of decimal odds (includes any bookmaker margin)."""
    if odds is None or not math.isfinite(odds) or odds <= 0.0:
        return float("nan")
    return 1.0 / odds


def american_to_decimal(a: float) -> float:
    """+175 -> 2.75 ; -175 -> 1.5714"""
    a = float(a)
    if a == 0:
        raise ValueError("American odds cannot be 0")
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / abs(a))


def decimal_to_american(d: float) -> int:
    if d >= 2.0:
        return int(round((d - 1.0) * 100.0))
    return int(round(-100.0 / (d - 1.0)))


def fractional_to_decimal(num: float, den: float) -> float:
    return 1.0 + float(num) / float(den)


_FRAC = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*$")


def parse_odds(text: object) -> Optional[float]:
    """Turn whatever a human types into decimal odds (or None if it makes no sense).

    Accepts: 1.28   1,28   +175   -150   5/2   74%
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        val = float(text)
        return val if val > 1.0 and math.isfinite(val) else None
    s = str(text).strip().replace(",", ".").replace(" ", "")
    if not s:
        return None
    try:
        m = _FRAC.match(s)
        if m:
            return fractional_to_decimal(float(m.group(1)), float(m.group(2)))
        if s.endswith("%"):
            p = float(s[:-1]) / 100.0
            return 1.0 / p if 0.0 < p < 1.0 else None
        if s[0] in "+-":
            v = float(s)
            return american_to_decimal(v) if abs(v) >= 100 else None
        v = float(s)
        return v if v > 1.0 else None
    except ValueError:
        return None


def fmt_odds(o: float) -> str:
    """1.2 -> '1.20'; big prices lose decimals like real sportsbooks."""
    if o is None or not math.isfinite(o):
        return "-"
    if o < 10:
        return f"{o:.2f}"
    if o < 100:
        return f"{o:.1f}"
    return f"{o:.0f}"


def fmt_pct(p: float, digits: int = 1) -> str:
    if p is None or not math.isfinite(p):
        return "-"
    return f"{100.0 * p:.{digits}f}%"


# ---------------------------------------------------------------- margin removal
def overround(odds: Sequence[float]) -> float:
    """Sum of implied probabilities minus 1 (0.05 = 5 % margin)."""
    return float(np.sum(1.0 / np.asarray(odds, dtype=float)) - 1.0)


def devig(odds: Sequence[float], method: str = "shin") -> np.ndarray:
    """Remove the bookmaker margin: returns fair probabilities that sum to exactly 1.

    proportional : divide every implied probability by the total (simple)
    power        : raise implied probabilities to a power g >= 1 so they sum to 1
    shin         : Shin (1993) - margin comes from insider trading; long shots get shaded more
    """
    pi = 1.0 / np.asarray(odds, dtype=float)
    total = pi.sum()
    if total <= 1.0 + 1e-12 or method == "proportional":
        return pi / total
    if method == "power":
        try:
            g = brentq(lambda g: float(np.sum(pi ** g) - 1.0), 1.0, 20.0)
            p = pi ** g
            return p / p.sum()
        except ValueError:
            return pi / total
    if method == "shin":
        def f(z: float) -> float:
            p = (np.sqrt(z * z + 4.0 * (1.0 - z) * pi * pi / total) - z) / (2.0 * (1.0 - z))
            return float(p.sum() - 1.0)
        try:
            z = brentq(f, 1e-9, 0.99)
        except ValueError:
            return pi / total
        p = (np.sqrt(z * z + 4.0 * (1.0 - z) * pi * pi / total) - z) / (2.0 * (1.0 - z))
        return p / p.sum()
    raise ValueError(f"unknown de-vig method: {method}")


# ---------------------------------------------------------------- value and staking
def edge(p: float, odds: float) -> float:
    """Expected profit per unit staked: p * odds - 1.  +0.05 means +5 % expected value."""
    return p * odds - 1.0


def kelly_fraction(p: float, odds: float, fraction: float = 0.25, cap: float = 0.05) -> float:
    """Fractional Kelly stake as a share of bankroll (0 when there is no edge).

    Full Kelly maximises long-run log growth: f* = (p*odds - 1) / (odds - 1).
    Quarter Kelly (fraction=0.25) keeps ~44 % of the growth with ~25 % of the volatility.
    """
    b = odds - 1.0
    if b <= 0 or p <= 0:
        return 0.0
    f_star = (p * odds - 1.0) / b
    if f_star <= 0:
        return 0.0
    return float(min(cap, fraction * f_star))


def clv_pct(odds_taken: float, closing_fair_prob: float) -> float:
    """Closing-line value: expected profit of the price you took, judged at the closing fair probability."""
    return odds_taken * closing_fair_prob - 1.0


def parlay_odds(odds: Sequence[float]) -> float:
    return float(np.prod(np.asarray(odds, dtype=float)))
