"""Team ratings for sports decided by point margins (basketball, American football).

    margin_home = h + r_home - r_away + noise(sd_margin)
    total       = b + t_home + t_away  + noise(sd_total)

Weighted ridge regression (closed form).  Ratings are in points; the ridge prior shrinks a team with
few games toward the league average, and the time-decay weight lets ratings follow form.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd


def _ridge(X: np.ndarray, y: np.ndarray, w: np.ndarray, reg: float, n_unpen: int) -> np.ndarray:
    A = X.T @ (X * w[:, None])
    pen = np.full(A.shape[0], reg)
    pen[:n_unpen] = 1e-9
    A = A + np.diag(pen)
    b = X.T @ (w * y)
    return np.linalg.solve(A, b)


@dataclass
class MarginModel:
    reg: float = 4.0
    xi: float = 0.004
    teams_: List[str] = field(default_factory=list)
    index_: Dict[str, int] = field(default_factory=dict)
    hfa_: float = 0.0
    base_total_: float = 0.0
    r_: np.ndarray = field(default_factory=lambda: np.zeros(0))
    t_: np.ndarray = field(default_factory=lambda: np.zeros(0))
    sd_margin_: float = 12.0
    sd_total_: float = 18.0
    n_: int = 0
    fitted_: bool = False

    def fit(self, df: pd.DataFrame, home_col: str = "home_score", away_col: str = "away_score",
            ref_date=None) -> "MarginModel":
        d = df.dropna(subset=["date", "home", "away", home_col, away_col]).copy()
        d["date"] = pd.to_datetime(d["date"])
        ref = pd.Timestamp(ref_date) if ref_date is not None else d["date"].max() + pd.Timedelta(days=1)
        d = d[d["date"] < ref]
        if len(d) < 20:
            raise ValueError("Need at least 20 games")
        teams = sorted(set(d["home"]).union(d["away"]))
        idx = {t: i for i, t in enumerate(teams)}
        n, m = len(teams), len(d)
        hi = d["home"].map(idx).to_numpy()
        ai = d["away"].map(idx).to_numpy()
        hs = d[home_col].to_numpy(float)
        as_ = d[away_col].to_numpy(float)
        age = (ref - d["date"]).dt.total_seconds().to_numpy() / 86400.0
        w = np.exp(-self.xi * np.maximum(age, 0.0))

        Xm = np.zeros((m, 1 + n))
        Xm[:, 0] = 1.0
        Xm[np.arange(m), 1 + hi] += 1.0
        Xm[np.arange(m), 1 + ai] -= 1.0
        Xt = np.zeros((m, 1 + n))
        Xt[:, 0] = 1.0
        Xt[np.arange(m), 1 + hi] += 1.0
        Xt[np.arange(m), 1 + ai] += 1.0
        margin, total = hs - as_, hs + as_
        bm = _ridge(Xm, margin, w, self.reg, 1)
        bt = _ridge(Xt, total, w, self.reg, 1)
        self.teams_, self.index_ = teams, idx
        self.hfa_, self.r_ = float(bm[0]), bm[1:]
        self.base_total_, self.t_ = float(bt[0]), bt[1:]
        rm, rt = margin - Xm @ bm, total - Xt @ bt
        self.sd_margin_ = float(np.sqrt(np.average(rm ** 2, weights=w)))
        self.sd_total_ = float(np.sqrt(np.average(rt ** 2, weights=w)))
        self.n_, self.fitted_ = int(m), True
        return self

    def has_team(self, team: str) -> bool:
        return team in self.index_

    def predict(self, home: str, away: str, neutral: bool = False) -> Dict[str, float]:
        ri = lambda t: float(self.r_[self.index_[t]]) if t in self.index_ else 0.0
        ti = lambda t: float(self.t_[self.index_[t]]) if t in self.index_ else 0.0
        return {"margin": (0.0 if neutral else self.hfa_) + ri(home) - ri(away),
                "total": self.base_total_ + ti(home) + ti(away),
                "sd_margin": self.sd_margin_, "sd_total": self.sd_total_}

    def table(self) -> pd.DataFrame:
        return pd.DataFrame({"team": self.teams_, "rating": self.r_, "scoring": self.t_}) \
            .sort_values("rating", ascending=False).reset_index(drop=True)
