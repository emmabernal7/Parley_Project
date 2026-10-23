import numpy as np
import pytest

from sportsquant.data.synthetic import simulate_soccer_league
from sportsquant.models.dixon_coles import DixonColes, _nll_grad, dc_grid


TEAMS = [f"Team{i:02d}" for i in range(16)]


def test_dc_grid_sums_to_one():
    g = dc_grid(1.7, 1.1, -0.08, 10)
    assert g.sum() == pytest.approx(1.0, abs=1e-9)
    assert (g >= 0).all()


def test_gradient_matches_finite_difference():
    df, _ = simulate_soccer_league(TEAMS, seasons=2, seed=3)
    m = DixonColes().fit(df)
    n = len(m.teams_)
    hi = df["home"].map(m.index_).to_numpy()
    ai = df["away"].map(m.index_).to_numpy()
    x, y = df["fthg"].to_numpy(float), df["ftag"].to_numpy(float)
    w = np.ones(len(df))
    theta = np.random.default_rng(0).normal(0, 0.1, 3 + 2 * n)
    theta[2 + 2 * n] = -0.08

    def f(t):
        return _nll_grad(t, hi, ai, x, y, w, n, 1.0)[0]

    _, analytic = _nll_grad(theta, hi, ai, x, y, w, n, 1.0)
    eps = 1e-6
    numeric = np.zeros_like(theta)
    for i in range(len(theta)):
        tp, tm = theta.copy(), theta.copy()
        tp[i] += eps
        tm[i] -= eps
        numeric[i] = (f(tp) - f(tm)) / (2 * eps)
    assert np.allclose(analytic, numeric, atol=5e-2, rtol=5e-3)


def test_recovers_known_parameters_on_synthetic_league():
    df, truth = simulate_soccer_league(TEAMS, seasons=5, seed=42, hfa=0.25, rho=-0.08)
    m = DixonColes(xi=0.0, reg=0.5).fit(df)
    assert m.converged_
    assert m.hfa_ == pytest.approx(truth["hfa"], abs=0.08)
    assert m.rho_ == pytest.approx(truth["rho"], abs=0.1)
    est = np.array([m.att_[m.index_[t]] for t in TEAMS])
    assert np.abs(est - truth["att"]).mean() < 0.1


def test_unfitted_team_falls_back_to_league_average():
    df, _ = simulate_soccer_league(TEAMS, seasons=3, seed=1)
    m = DixonColes().fit(df)
    assert not m.has_team("Nobody FC")
    lam, mu = m.rates("Nobody FC", "Team01")
    assert lam > 0 and mu > 0


def test_fit_requires_minimum_matches():
    import pandas as pd
    tiny = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=3), "home": ["A", "B", "A"],
                        "away": ["B", "A", "B"], "fthg": [1, 0, 2], "ftag": [0, 1, 1]})
    with pytest.raises(ValueError):
        DixonColes().fit(tiny)
