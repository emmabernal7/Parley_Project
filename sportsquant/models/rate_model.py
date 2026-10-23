"""Count model for cards, corners, fouls (and goals/runs in hockey and baseball).

    ln E[home count] = c + h + f_home - g_away + r_ref
    ln E[away count] = c     + f_away - g_home + r_ref

    f_i : how many the team tends to PRODUCE   (a "dirty" team has a large f for cards)
    g_j : how many the team tends to CONCEDE / ALLOW (the tendency of the opponent to induce them)
    r   : referee effect (a card-happy referee has r > 0), shrunk toward 0 by a Gaussian prior

Fitted like Dixon-Coles: weighted, ridge-regularised Poisson maximum likelihood with an analytic
gradient.  Predictions use a negative binomial whose extra spread (alpha) is estimated from the
residuals, because real card / corner counts are a little more spread out than a Poisson.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ..mathutil import nb_pmf


def _nll_grad(theta, hi, ai, ri, x, y, w, n, m, reg, reg_ref):
    c, hfa = theta[0], theta[1]
    f = theta[2:2 + n]
    g = theta[2 + n:2 + 2 * n]
    r = theta[2 + 2 * n:2 + 2 * n + m]

    has_ref = ri >= 0
    rr = np.where(has_ref, r[np.where(has_ref, ri, 0)] if m else 0.0, 0.0)
    u = c + hfa + f[hi] - g[ai] + rr
    v = c + f[ai] - g[hi] + rr
    lam, mu = np.exp(u), np.exp(v)

    ll = np.sum(w * (x * u - lam + y * v - mu))
    du, dv = w * (x - lam), w * (y - mu)

    grad = np.zeros_like(theta)
    grad[0] = du.sum() + dv.sum()
    grad[1] = du.sum()
    grad[2:2 + n] = np.bincount(hi, weights=du, minlength=n) + np.bincount(ai, weights=dv, minlength=n)
    grad[2 + n:2 + 2 * n] = -np.bincount(ai, weights=du, minlength=n) - np.bincount(hi, weights=dv, minlength=n)
    if m:
        grad[2 + 2 * n:] = np.bincount(ri[has_ref], weights=(du + dv)[has_ref], minlength=m)

    ll -= reg * (f @ f + g @ g) + reg_ref * (r @ r)
    grad[2:2 + n] -= 2.0 * reg * f
    grad[2 + n:2 + 2 * n] -= 2.0 * reg * g
    if m:
        grad[2 + 2 * n:] -= 2.0 * reg_ref * r
    return -ll, -grad


@dataclass
class RateModel:
    xi: float = 0.0019
    reg: float = 1.0
    reg_ref: float = 3.0
    teams_: List[str] = field(default_factory=list)
    index_: Dict[str, int] = field(default_factory=dict)
    refs_: List[str] = field(default_factory=list)
    ref_index_: Dict[str, int] = field(default_factory=dict)
    ref_counts_: Dict[str, int] = field(default_factory=dict)
    c_: float = 0.0
    hfa_: float = 0.0
    f_: np.ndarray = field(default_factory=lambda: np.zeros(0))
    g_: np.ndarray = field(default_factory=lambda: np.zeros(0))
    r_: np.ndarray = field(default_factory=lambda: np.zeros(0))
    alpha_: float = 0.0
    n_matches_: int = 0
    fitted_: bool = False

    def fit(self, df: pd.DataFrame, y_home: str, y_away: str, ref_col: Optional[str] = None,
            ref_date=None) -> "RateModel":
        need = ["date", "home", "away", y_home, y_away]
        d = df.dropna(subset=need).copy()
        d["date"] = pd.to_datetime(d["date"])
        ref = pd.Timestamp(ref_date) if ref_date is not None else (d["date"].max() + pd.Timedelta(days=1))
        d = d[d["date"] < ref]
        if len(d) < 20:
            raise ValueError("Need at least 20 matches to fit the count model")

        teams = sorted(set(d["home"]).union(d["away"]))
        idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        hi = d["home"].map(idx).to_numpy()
        ai = d["away"].map(idx).to_numpy()
        x = d[y_home].to_numpy(dtype=float)
        y = d[y_away].to_numpy(dtype=float)
        age = (ref - d["date"]).dt.total_seconds().to_numpy() / 86400.0
        w = np.exp(-self.xi * np.maximum(age, 0.0))

        if ref_col and ref_col in d.columns:
            names = d[ref_col].fillna("").astype(str).str.strip()
            refs = sorted({r for r in names if r})
            ref_idx = {r: i for i, r in enumerate(refs)}
            ri = names.map(lambda r: ref_idx.get(r, -1)).to_numpy()
            counts = names[names != ""].value_counts().to_dict()
        else:
            refs, ref_idx, ri, counts = [], {}, np.full(len(d), -1), {}
        m = len(refs)

        theta0 = np.zeros(2 + 2 * n + m)
        theta0[0] = np.log(max(np.average((x + y) / 2.0, weights=w), 0.05))
        res = minimize(_nll_grad, theta0, args=(hi, ai, ri, x, y, w, n, m, self.reg, self.reg_ref),
                       jac=True, method="L-BFGS-B", options={"maxiter": 500})
        th = res.x
        self.teams_, self.index_ = teams, idx
        self.refs_, self.ref_index_, self.ref_counts_ = refs, ref_idx, {k: int(v) for k, v in counts.items()}
        self.c_, self.hfa_ = float(th[0]), float(th[1])
        self.f_, self.g_ = th[2:2 + n].copy(), th[2 + n:2 + 2 * n].copy()
        self.r_ = th[2 + 2 * n:].copy()
        self.n_matches_ = int(len(d))

        # overdispersion: Var = mean * (1 + alpha * mean)  ->  alpha from Pearson residuals
        has = ri >= 0
        rr = np.where(has, self.r_[np.where(has, ri, 0)] if m else 0.0, 0.0)
        mh = np.exp(self.c_ + self.hfa_ + self.f_[hi] - self.g_[ai] + rr)
        ma = np.exp(self.c_ + self.f_[ai] - self.g_[hi] + rr)
        num = np.sum(w * ((x - mh) ** 2 - mh)) + np.sum(w * ((y - ma) ** 2 - ma))
        den = np.sum(w * mh ** 2) + np.sum(w * ma ** 2)
        self.alpha_ = float(max(0.0, num / den)) if den > 0 else 0.0
        self.fitted_ = True
        return self

    # ---------------------------------------------------------------- predict
    def _s(self, team: str) -> Tuple[float, float]:
        i = self.index_.get(team)
        return (0.0, 0.0) if i is None else (float(self.f_[i]), float(self.g_[i]))

    def ref_effect(self, referee: Optional[str]) -> float:
        if not referee:
            return 0.0
        i = self.ref_index_.get(str(referee).strip())
        return 0.0 if i is None else float(self.r_[i])

    def rates(self, home: str, away: str, referee: Optional[str] = None) -> Tuple[float, float]:
        fh, gh = self._s(home)
        fa, ga = self._s(away)
        r = self.ref_effect(referee)
        return (float(np.exp(self.c_ + self.hfa_ + fh - ga + r)), float(np.exp(self.c_ + fa - gh + r)))

    def pmfs(self, home: str, away: str, referee: Optional[str] = None, kmax: int = 40):
        mh, ma = self.rates(home, away, referee)
        return nb_pmf(mh, self.alpha_, kmax), nb_pmf(ma, self.alpha_, kmax)

    def total_pmf(self, home: str, away: str, referee: Optional[str] = None, kmax: int = 40) -> np.ndarray:
        ph, pa = self.pmfs(home, away, referee, kmax)
        t = np.convolve(ph, pa)
        return t / t.sum()

    def referee_table(self) -> pd.DataFrame:
        """Referee effect as a multiplier (1.20 = 20 % more than the average referee)."""
        rows = [{"referee": r, "multiplier": float(np.exp(self.r_[i])), "matches": self.ref_counts_.get(r, 0)}
                for r, i in self.ref_index_.items()]
        return pd.DataFrame(rows).sort_values("multiplier", ascending=False).reset_index(drop=True)

    def team_table(self) -> pd.DataFrame:
        return pd.DataFrame({"team": self.teams_, "produces": np.exp(self.f_), "concedes": np.exp(self.g_)})
