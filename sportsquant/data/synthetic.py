"""Synthetic leagues with KNOWN parameters.

Why this exists: to test a fitting program you generate data from a model whose parameters you
know, fit it, and check the parameters come back (the same trick as testing a Monte Carlo code
against an exactly solvable model).  The same generator also feeds the offline demo universe.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..models.dixon_coles import dc_grid


def round_robin(n: int) -> List[List[Tuple[int, int]]]:
    """Double round robin by the circle method (n even): list of rounds of (home, away) index pairs."""
    if n % 2:
        raise ValueError("n must be even")
    idx = list(range(n))
    rounds = []
    for r in range(n - 1):
        pairs = []
        for k in range(n // 2):
            a, b = idx[k], idx[n - 1 - k]
            pairs.append((a, b) if (r + k) % 2 == 0 else (b, a))
        rounds.append(pairs)
        idx = [idx[0]] + [idx[-1]] + idx[1:-1]
    return rounds + [[(b, a) for a, b in rd] for rd in rounds]


def sample_nb(rng: np.random.Generator, mean: np.ndarray, alpha: float) -> np.ndarray:
    """Negative-binomial counts via the Gamma-Poisson mixture (alpha = 0 gives Poisson)."""
    mean = np.asarray(mean, dtype=float)
    if alpha <= 1e-9:
        return rng.poisson(mean)
    shape = 1.0 / alpha
    return rng.poisson(rng.gamma(shape, mean / shape))


def simulate_soccer_league(teams: Sequence[str], seasons: int = 3, seed: int = 0, c: float = 0.17,
                           hfa: float = 0.25, rho: float = -0.08, att_sd: float = 0.25, dfc_sd: float = 0.2,
                           start: date = date(2021, 8, 7), league: str = "SIM",
                           referees: Optional[Sequence[str]] = None, alpha_cards: float = 0.10,
                           alpha_corners: float = 0.06) -> Tuple[pd.DataFrame, Dict]:
    """Returns (matches DataFrame, truth dict).  Columns follow the football-data conventions."""
    rng = np.random.default_rng(seed)
    n = len(teams)
    att = rng.normal(0, att_sd, n)
    dfc = rng.normal(0, dfc_sd, n)
    att -= att.mean()
    dfc -= dfc.mean()
    # count-model truth: team "produces" and "concedes" cards / corners, referee effect on cards
    f_card = rng.normal(0, 0.15, n)
    g_card = rng.normal(0, 0.10, n)
    f_cor = rng.normal(0, 0.12, n)
    g_cor = rng.normal(0, 0.10, n)
    refs = list(referees) if referees else []
    r_card = rng.normal(0, 0.18, len(refs)) if refs else np.zeros(0)

    rows = []
    rounds = round_robin(n)
    for s in range(seasons):
        season_start = start + timedelta(days=365 * s)
        order = rng.permutation(len(rounds))
        for k, ridx in enumerate(order):
            day = season_start + timedelta(days=7 * k)
            for (h, a) in rounds[ridx]:
                lam = np.exp(c + hfa + att[h] - dfc[a])
                mu = np.exp(c + att[a] - dfc[h])
                g = dc_grid(lam, mu, rho, 10)
                flat = rng.choice(g.size, p=g.ravel())
                x, y = divmod(int(flat), g.shape[1])
                ref_i = int(rng.integers(len(refs))) if refs else -1
                rc = r_card[ref_i] if ref_i >= 0 else 0.0
                cards_h = sample_nb(rng, np.exp(np.log(1.7) + 0.10 + f_card[h] - g_card[a] + rc), alpha_cards)
                cards_a = sample_nb(rng, np.exp(np.log(1.7) + f_card[a] - g_card[h] + rc), alpha_cards)
                cor_h = sample_nb(rng, np.exp(np.log(5.0) + 0.15 + f_cor[h] - g_cor[a]), alpha_corners)
                cor_a = sample_nb(rng, np.exp(np.log(5.0) + f_cor[a] - g_cor[h]), alpha_corners)
                rows.append({
                    "date": pd.Timestamp(day), "league": league, "season": start.year + s,
                    "home": teams[h], "away": teams[a], "fthg": x, "ftag": y,
                    "hthg": int(rng.binomial(x, 0.45)), "htag": int(rng.binomial(y, 0.45)),
                    "hc": int(cor_h), "ac": int(cor_a), "hy": int(cards_h), "ay": int(cards_a),
                    "hr": 0, "ar": 0, "referee": refs[ref_i] if refs else None,
                })
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    truth = {"teams": list(teams), "c": c, "hfa": hfa, "rho": rho, "att": att, "dfc": dfc,
             "refs": refs, "r_card": r_card, "f_card": f_card, "g_card": g_card}
    return df, truth
