import numpy as np
import pytest

from sportsquant.models.dixon_coles import dc_grid
from sportsquant.markets.scoredist import ScoreDist, split_line


@pytest.fixture()
def dist():
    return ScoreDist(dc_grid(1.7, 1.1, -0.08, 10))


def test_1x2_sums_to_one(dist):
    assert sum(dist.p_1x2()) == pytest.approx(1.0, abs=1e-9)


def test_double_chance_consistent_with_1x2(dist):
    ph, pd_, pa = dist.p_1x2()
    dc = dist.p_double_chance()
    assert dc["1x"] == pytest.approx(ph + pd_)
    assert dc["12"] == pytest.approx(ph + pa)
    assert dc["x2"] == pytest.approx(pd_ + pa)


def test_btts_and_clean_sheets_are_complementary(dist):
    b = dist.p_btts()
    cs_home = dist.p_clean_sheet("home")
    assert 0 < b < 1
    assert cs_home + b <= 1 + 1e-9


def test_over_under_partition(dist):
    o, push, u = dist.p_over(2.5)
    assert push == 0.0
    assert o + u == pytest.approx(1.0, abs=1e-9)


def test_split_line_quarter_vs_whole():
    assert split_line(1.0) == [1.0]
    assert split_line(-0.25) == [-0.5, 0.0]
    assert split_line(0.75) == [0.5, 1.0]


def test_asian_handicap_whole_line_can_push():
    d = ScoreDist(dc_grid(1.3, 1.3, -0.05, 10))
    s = d.asian_handicap(0.0, "home")
    assert s.push == pytest.approx(d.p(d.D == 0))
    assert s.win + s.loss + s.push == pytest.approx(1.0, abs=1e-9)


def test_asian_handicap_quarter_line_half_win_half_loss():
    d = ScoreDist(dc_grid(1.5, 1.2, -0.05, 10))
    s = d.asian_handicap(-0.25, "home")
    total_mass_on_draw = d.p(d.D == 0)
    assert s.half_loss == pytest.approx(total_mass_on_draw, abs=1e-9)


def test_correct_scores_sorted_and_bounded(dist):
    cs = dist.correct_scores(5)
    probs = [p for _, p in cs]
    assert probs == sorted(probs, reverse=True)
    assert sum(probs) < 1.0


def test_joint_leg_matches_manual_mask():
    d = ScoreDist(dc_grid(1.8, 0.9, -0.08, 10))
    joint = d.joint([{"market": "1x2", "selection": "home"}, {"market": "total", "line": 2.5, "selection": "over"}])
    manual = d.p((d.D > 0) & (d.T > 2.5))
    assert joint == pytest.approx(manual)


def test_joint_differs_from_naive_product_when_correlated():
    d = ScoreDist(dc_grid(2.2, 0.6, -0.1, 10))
    home_win = d.joint([{"market": "1x2", "selection": "home"}])
    btts_yes = d.joint([{"market": "btts", "selection": "yes"}])
    joint = d.joint([{"market": "1x2", "selection": "home"}, {"market": "btts", "selection": "yes"}])
    assert joint != pytest.approx(home_win * btts_yes, rel=1e-3)


def test_joint_rejects_whole_line_leg():
    d = ScoreDist(dc_grid(1.5, 1.0, -0.05, 10))
    with pytest.raises(ValueError):
        d.joint([{"market": "total", "line": 2.0, "selection": "over"}])
