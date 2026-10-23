import numpy as np
import pytest
from scipy.stats import poisson

from sportsquant.inplay.soccer import (InPlayParams, SoccerState, calibrate_scale, inplay_dist,
                                       lead_hit_prob, make_tilt, remaining_weights, run_dp)
from sportsquant.models.dixon_coles import dc_grid
from sportsquant.markets.scoredist import ScoreDist


def test_beta_zero_matches_independent_poisson():
    p = InPlayParams(beta_score=0.0)
    lam, mu = 1.9, 0.9
    st = SoccerState(phase="h2", minute=60, home=1, away=0)
    w = remaining_weights(p, st)
    g = run_dp(lam, mu, st, w, p)
    K = g.shape[0]
    ref = np.outer(poisson.pmf(np.arange(K), lam * w.sum()), poisson.pmf(np.arange(K), mu * w.sum()))
    ref /= ref.sum()
    assert np.abs(g - ref).max() < 1e-6


def test_kickoff_tilt_matches_pretmatch_dixon_coles_exactly():
    lam, mu, rho = 2.4, 0.55, -0.08
    p = InPlayParams()
    scale = calibrate_scale(lam, mu, p)
    tilt = make_tilt(lam, mu, rho, p, scale)
    at_kickoff = inplay_dist(lam, mu, SoccerState(), p, scale, tilt)
    pre_match = ScoreDist(dc_grid(lam, mu, rho, 10))
    assert at_kickoff.p_1x2() == pytest.approx(pre_match.p_1x2(), abs=1e-4)
    assert at_kickoff.p_over(2.5)[0] == pytest.approx(pre_match.p_over(2.5)[0], abs=1e-4)


def test_probabilities_sum_to_one_throughout_a_match():
    lam, mu = 1.6, 1.3
    p = InPlayParams()
    scale = calibrate_scale(lam, mu, p)
    for state in [SoccerState(), SoccerState(phase="h1", minute=20, home=1),
                 SoccerState(phase="h2", minute=70, home=1, away=1, red_home=1)]:
        d = inplay_dist(lam, mu, state, p, scale)
        assert d.G.sum() == pytest.approx(1.0, abs=1e-9)


def test_favourite_two_up_shortens_price():
    lam, mu = 2.4, 0.55
    p = InPlayParams()
    scale = calibrate_scale(lam, mu, p)
    pre = inplay_dist(lam, mu, SoccerState(), p, scale)
    two_up = inplay_dist(lam, mu, SoccerState(phase="h1", minute=30, home=2), p, scale)
    assert two_up.p_1x2()[0] > pre.p_1x2()[0]  # home win probability increases after going 2-0 up


def test_lead_hit_probability_matches_monte_carlo_when_score_effects_off():
    p = InPlayParams(beta_score=0.0)
    lam, mu = 1.8, 1.0
    scale = (1.0, 1.0)
    analytic = lead_hit_prob(lam, mu, SoccerState(), p, scale, 1, "home")
    rng = np.random.default_rng(0)
    w = remaining_weights(p, SoccerState())
    cdf = np.cumsum(w)
    hits = 0
    trials = 4000
    for _ in range(trials):
        nh, na = rng.poisson(lam), rng.poisson(mu)
        th = np.searchsorted(cdf, rng.random(nh))
        ta = np.searchsorted(cdf, rng.random(na))
        seq = sorted([(t, 1) for t in th] + [(t, -1) for t in ta], key=lambda z: (z[0], rng.random()))
        d = 0
        led = False
        for _, s in seq:
            d += s
            led = led or d >= 1
        hits += led
    mc = hits / trials
    assert analytic == pytest.approx(mc, abs=0.03)


def test_already_two_up_returns_one():
    p = InPlayParams()
    scale = (1.0, 1.0)
    st = SoccerState(phase="h2", minute=70, home=3, away=1)
    assert lead_hit_prob(1.0, 1.0, st, p, scale, 2, "home") == 1.0
