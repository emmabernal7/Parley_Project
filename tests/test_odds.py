import numpy as np
import pytest

from sportsquant.odds import (american_to_decimal, clv_pct, decimal_to_american, devig, edge,
                              fractional_to_decimal, kelly_fraction, overround, parlay_odds,
                              parse_odds, prob_to_odds)


def test_prob_odds_are_inverses():
    for p in (0.1, 0.3, 0.5, 0.75, 0.99):
        assert prob_to_odds(p) == pytest.approx(1.0 / p)


def test_american_odds_conversion():
    assert american_to_decimal(150) == pytest.approx(2.5)
    assert american_to_decimal(-150) == pytest.approx(1.6667, abs=1e-3)
    assert decimal_to_american(2.5) == 150
    assert decimal_to_american(1.6667) == pytest.approx(-150, abs=1)


def test_fractional_odds():
    assert fractional_to_decimal(5, 2) == 3.5


def test_parse_odds_accepts_multiple_formats():
    assert parse_odds("1.90") == pytest.approx(1.90)
    assert parse_odds("1,90") == pytest.approx(1.90)
    assert parse_odds("+150") == pytest.approx(2.5)
    assert parse_odds("-150") == pytest.approx(1.6667, abs=1e-3)
    assert parse_odds("5/2") == pytest.approx(3.5)
    assert parse_odds("40%") == pytest.approx(2.5)
    assert parse_odds("nonsense") is None
    assert parse_odds("0.5") is None  # odds must be > 1


def test_overround_positive_for_real_book():
    assert overround([1.9, 3.6, 4.2]) > 0


def test_devig_methods_sum_to_one():
    odds = [1.9, 3.6, 4.2]
    for method in ("proportional", "power", "shin"):
        p = devig(odds, method)
        assert p.sum() == pytest.approx(1.0, abs=1e-6)
        assert (p > 0).all()


def test_shin_shades_longshots_more_than_proportional():
    odds = [1.2, 6.0, 15.0]
    p_prop = devig(odds, "proportional")
    p_shin = devig(odds, "shin")
    # Shin's method should lower the longshot's fair probability relative to proportional
    assert p_shin[-1] <= p_prop[-1] + 1e-9


def test_edge_and_kelly():
    assert edge(0.6, 2.0) == pytest.approx(0.2)
    assert kelly_fraction(0.5, 1.5, fraction=1.0) == 0.0  # negative edge -> no stake
    f = kelly_fraction(0.6, 2.0, fraction=1.0, cap=1.0)
    assert f == pytest.approx(0.2)
    f_quarter = kelly_fraction(0.6, 2.0, fraction=0.25, cap=1.0)
    assert f_quarter == pytest.approx(0.05)


def test_kelly_capped():
    f = kelly_fraction(0.9, 5.0, fraction=1.0, cap=0.05)
    assert f == 0.05


def test_clv_and_parlay_odds():
    assert clv_pct(2.0, 0.55) == pytest.approx(0.1)
    assert parlay_odds([2.0, 1.5, 3.0]) == pytest.approx(9.0)
