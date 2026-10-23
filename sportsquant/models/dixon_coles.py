"""Dixon-Coles (1997) goals model.

THE PROBABILITY FUNCTION WE FIT
-------------------------------
For a match with home team i and away team j the goals (X, Y) follow

    P(X = x, Y = y) = tau(x, y) * Poisson(x; lam) * Poisson(y; mu)

    ln lam = c + h + a_i - d_j          (home scoring rate: attack of i vs defence of j, + home edge h)
    ln mu  = c     + a_j - d_i          (away scoring rate)

    tau(0,0) = 1 - lam*mu*rho    tau(0,1) = 1 + lam*rho
    tau(1,0) = 1 + mu*rho        tau(1,1) = 1 - rho        tau = 1 otherwise

The Poisson factors are the "radioactive decay" part (rare independent events at constant rate);
rho is a small correction because real 0-0 / 1-1 draws are slightly more (rho<0) or less common
than independence predicts.

HOW IT IS FITTED
----------------
Maximise the log-likelihood, weighting each match by w = exp(-xi * age_in_days) (recent matches
count more; xi = 0.0019 gives a one-year half-life) and adding a Gaussian prior (ridge) on the
team strengths so teams with few matches shrink toward the league average:

    L(theta) = sum_m w_m [ ln tau_m + x_m ln lam_m - lam_m + y_m ln mu_m - mu_m ]
               - reg * (sum_i a_i^2 + sum_i d_i^2)

The gradient is analytic (see _nll_grad) and checked against finite differences in the tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ..mathutil import pois_pmf

RHO_MAX = 0.25


def dc_grid(lam: float, mu: float, rho: float = 0.0, max_goals: int = 10) -> np.ndarray:
    """Joint scoreline probabilities G[x, y] = P(home x, away y), normalised to sum to 1."""
    g = np.outer(pois_pmf(lam, max_goals), pois_pmf(mu, max_goals))
    g[0, 0] *= 1.0 - lam * mu * rho
    g[0, 1] *= 1.0 + lam * rho
    g[1, 0] *= 1.0 + mu * rho
    g[1, 1] *= 1.0 - rho
    g = np.clip(g, 0.0, None)
    return g / g.sum()


def _nll_grad(theta, hi, ai, x, y, w, n, reg):
    """Negative log-likelihood and its analytic gradient."""
    c, hfa = theta[0], theta[1]
    att = theta[2:2 + n]
    dfc = theta[2 + n:2 + 2 * n]
    rho = theta[2 + 2 * n]

    u = c + hfa + att[hi] - dfc[ai]          # ln lam
    v = c + att[ai] - dfc[hi]                # ln mu
    lam = np.exp(u)
    mu = np.exp(v)

    ll = np.sum(w * (x * u - lam + y * v - mu))
    du = w * (x - lam)
    dv = w * (y - mu)

    logtau = np.zeros_like(lam)
    dtu = np.zeros_like(lam)     # d ln tau / d u
    dtv = np.zeros_like(lam)     # d ln tau / d v
    dtr = np.zeros_like(lam)     # d ln tau / d rho

    m = (x == 0) & (y == 0)
    if m.any():
        t = np.maximum(1.0 - lam[m] * mu[m] * rho, 1e-9)
        logtau[m] = np.log(t)
        dtu[m] = -lam[m] * mu[m] * rho / t
        dtv[m] = dtu[m]
        dtr[m] = -lam[m] * mu[m] / t
    m = (x == 0) & (y == 1)
    if m.any():
        t = np.maximum(1.0 + lam[m] * rho, 1e-9)
        logtau[m] = np.log(t)
        dtu[m] = lam[m] * rho / t
        dtr[m] = lam[m] / t
    m = (x == 1) & (y == 0)
    if m.any():
        t = np.maximum(1.0 + mu[m] * rho, 1e-9)
        logtau[m] = np.log(t)
        dtv[m] = mu[m] * rho / t
        dtr[m] = mu[m] / t
    m = (x == 1) & (y == 1)
    if m.any():
        t = np.maximum(1.0 - rho, 1e-9)
        logtau[m] = np.log(t)
        dtr[m] = -1.0 / t

    ll += np.sum(w * logtau)
    du = du + w * dtu
    dv = dv + w * dtv

    g = np.zeros_like(theta)
    g[0] = du.sum() + dv.sum()
    g[1] = du.sum()
    g[2:2 + n] = np.bincount(hi, weights=du, minlength=n) + np.bincount(ai, weights=dv, minlength=n)
    g[2 + n:2 + 2 * n] = -np.bincount(ai, weights=du, minlength=n) - np.bincount(hi, weights=dv, minlength=n)
    g[2 + 2 * n] = np.sum(w * dtr)

    ll -= reg * (att @ att + dfc @ dfc)
    g[2:2 + n] -= 2.0 * reg * att
    g[2 + n:2 + 2 * n] -= 2.0 * reg * dfc
    return -ll, -g


@dataclass
class DixonColes:
    xi: float = 0.0019
    reg: float = 1.0
    max_goals: int = 10
    teams_: List[str] = field(default_factory=list)
    index_: Dict[str, int] = field(default_factory=dict)
    c_: float = 0.15
    hfa_: float = 0.25
    att_: np.ndarray = field(default_factory=lambda: np.zeros(0))
    dfc_: np.ndarray = field(default_factory=lambda: np.zeros(0))
    rho_: float = -0.05
    n_matches_: int = 0
    n_eff_: float = 0.0
    converged_: bool = False
    fitted_: bool = False

    # ------------------------------------------------------------------ fit
    def fit(self, df: pd.DataFrame, ref_date=None, init: Optional["DixonColes"] = None) -> "DixonColes":
        """df needs columns: date, home, away, fthg, ftag.  Only rows strictly before ref_date are used."""
        d = df.dropna(subset=["date", "home", "away", "fthg", "ftag"]).copy()
        d["date"] = pd.to_datetime(d["date"])
        if ref_date is None:
            ref = d["date"].max() + pd.Timedelta(days=1) if len(d) else pd.Timestamp.today()
        else:
            ref = pd.Timestamp(ref_date)
        d = d[d["date"] < ref]
        if len(d) < 10:
            raise ValueError("Need at least 10 matches to fit Dixon-Coles")

        teams = sorted(set(d["home"]).union(d["away"]))
        idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        hi = d["home"].map(idx).to_numpy()
        ai = d["away"].map(idx).to_numpy()
        x = d["fthg"].to_numpy(dtype=float)
        y = d["ftag"].to_numpy(dtype=float)
        age = (ref - d["date"]).dt.total_seconds().to_numpy() / 86400.0
        w = np.exp(-self.xi * np.maximum(age, 0.0))

        theta0 = np.zeros(3 + 2 * n)
        theta0[0] = np.log(max(np.average((x + y) / 2.0, weights=w), 0.2))
        theta0[1] = 0.2
        theta0[2 + 2 * n] = -0.05
        if init is not None and init.fitted_:
            theta0[0], theta0[1], theta0[2 + 2 * n] = init.c_, init.hfa_, init.rho_
            for t, i in idx.items():
                j = init.index_.get(t)
                if j is not None:
                    theta0[2 + i] = init.att_[j]
                    theta0[2 + n + i] = init.dfc_[j]

        bounds = [(-3, 3), (-1, 1)] + [(-3, 3)] * (2 * n) + [(-RHO_MAX, RHO_MAX)]
        res = minimize(_nll_grad, theta0, args=(hi, ai, x, y, w, n, self.reg), jac=True,
                       method="L-BFGS-B", bounds=bounds, options={"maxiter": 500})
        th = res.x
        self.teams_, self.index_ = teams, idx
        self.c_, self.hfa_ = float(th[0]), float(th[1])
        self.att_, self.dfc_ = th[2:2 + n].copy(), th[2 + n:2 + 2 * n].copy()
        self.rho_ = float(th[2 + 2 * n])
        self.n_matches_, self.n_eff_ = int(len(d)), float(w.sum())
        self.converged_, self.fitted_ = bool(res.success), True
        return self

    # ------------------------------------------------------------------ predict
    def has_team(self, team: str) -> bool:
        return team in self.index_

    def strengths(self, team: str) -> Tuple[float, float]:
        """(attack, defence) log-strengths; unknown teams count as league average (0, 0)."""
        i = self.index_.get(team)
        if i is None:
            return 0.0, 0.0
        return float(self.att_[i]), float(self.dfc_[i])

    def rates(self, home: str, away: str, neutral: bool = False) -> Tuple[float, float]:
        ah, dh = self.strengths(home)
        aa, da = self.strengths(away)
        lam = np.exp(self.c_ + (0.0 if neutral else self.hfa_) + ah - da)
        mu = np.exp(self.c_ + aa - dh)
        return float(lam), float(mu)

    def grid(self, home: str, away: str, neutral: bool = False, scale: Tuple[float, float] = (1.0, 1.0)) -> np.ndarray:
        lam, mu = self.rates(home, away, neutral)
        return dc_grid(lam * scale[0], mu * scale[1], self.rho_, self.max_goals)

    def league_rates(self) -> Tuple[float, float]:
        """Goals for an average home / away team against an average opponent."""
        return float(np.exp(self.c_ + self.hfa_)), float(np.exp(self.c_))

    def table(self) -> pd.DataFrame:
        """Team strengths sorted by overall strength (attack + defence)."""
        df = pd.DataFrame({"team": self.teams_, "attack": self.att_, "defence": self.dfc_})
        df["overall"] = df["attack"] + df["defence"]
        return df.sort_values("overall", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------ persistence
    def to_dict(self) -> dict:
        return {"xi": self.xi, "reg": self.reg, "max_goals": self.max_goals, "teams": self.teams_,
                "c": self.c_, "hfa": self.hfa_, "att": self.att_.tolist(), "dfc": self.dfc_.tolist(),
                "rho": self.rho_, "n_matches": self.n_matches_, "n_eff": self.n_eff_}

    @classmethod
    def from_dict(cls, d: dict) -> "DixonColes":
        m = cls(xi=d["xi"], reg=d["reg"], max_goals=d["max_goals"])
        m.teams_ = list(d["teams"])
        m.index_ = {t: i for i, t in enumerate(m.teams_)}
        m.c_, m.hfa_, m.rho_ = d["c"], d["hfa"], d["rho"]
        m.att_, m.dfc_ = np.array(d["att"]), np.array(d["dfc"])
        m.n_matches_, m.n_eff_ = d.get("n_matches", 0), d.get("n_eff", 0.0)
        m.fitted_ = True
        m.converged_ = True
        return m
