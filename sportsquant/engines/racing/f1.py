"""Motorsport / Formula 1 Monte Carlo simulation engine."""
from __future__ import annotations

import hashlib
from typing import Dict, List, Sequence

import numpy as np

from ...events import Event
from ...markets.schema import finalize, group, sel


class F1Engine:
    """Race outcome by Monte Carlo: utility = driver rating - grid penalty + Gumbel noise; DNF risk per driver."""

    def __init__(self, race_id: str, field: List[Dict], n_sim: int = 20000, grid_weight: float = 0.22,
                 noise: float = 1.0, model_label: str = "Rating + grid Monte Carlo", confidence: str = "ok"):
        self.field, self.n_sim, self.gw, self.noise = field, n_sim, grid_weight, noise
        self.seed = int(hashlib.md5(race_id.encode()).hexdigest()[:8], 16)
        self.model_label, self.confidence = model_label, confidence

    def simulate(self) -> Dict[str, np.ndarray]:
        rng = np.random.default_rng(self.seed)
        n = len(self.field)
        rating = np.array([float(d.get("rating", 0.0)) for d in self.field])
        grid = np.array([float(d.get("grid", i + 1)) for i, d in enumerate(self.field)])
        dnf = np.array([float(d.get("dnf", 0.08)) for d in self.field])
        u = rating[None, :] - self.gw * (grid[None, :] - 1) + rng.gumbel(0.0, self.noise, size=(self.n_sim, n))
        u = np.where(rng.random((self.n_sim, n)) < dnf[None, :], -1e9 + rng.random((self.n_sim, n)), u)
        order = np.argsort(-u, axis=1)
        pos = np.empty_like(order)
        rows = np.arange(self.n_sim)[:, None]
        pos[rows, order] = np.arange(n)[None, :]
        return {"pos": pos}

    def info(self, ev: Event) -> Dict:
        return {"model": self.model_label, "confidence": self.confidence}

    def markets(self, ev: Event) -> List[Dict]:
        pos = self.simulate()["pos"]
        names = [d["name"] for d in self.field]
        def top(k: int) -> np.ndarray:
            return (pos < k).mean(axis=0)
        win, pod, t6, pts = top(1), top(3), top(6), top(10)
        order = np.argsort(-win)[:12]
        groups = [group("winner", "Race Winner", "main", [sel(f"d{i}", names[i], win[i]) for i in order]),
                  group("podium", "Podium Finish (Top 3)", "main",
                        [sel(f"d{i}", names[i], pod[i]) for i in np.argsort(-pod)[:12]], kind="multi",
                        note="Each driver is an independent yes/no bet."),
                  group("top6", "Top 6 Finish", "lines", [sel(f"d{i}", names[i], t6[i]) for i in np.argsort(-t6)[:12]]),
                  group("points", "Points Finish (Top 10)", "lines",
                        [sel(f"d{i}", names[i], pts[i]) for i in np.argsort(-pts)[:14]])]
        return finalize(groups)

    @staticmethod
    def headline(groups: Sequence[Dict]) -> Dict:
        for g in groups:
            if g["id"] == "winner":
                return {"field": [{"label": s["label"], "prob": s["prob"]} for s in g["selections"][:3]]}
        return {}
