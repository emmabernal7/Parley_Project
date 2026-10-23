import pytest

from sportsquant.models.racket import (game_win_prob, rally_prob_for_win, serve_probs_for_win,
                                       set_dist, tennis_match, volleyball_match)


def test_game_win_prob_matches_textbook_value():
    # a well-known closed-form check: p=0.6 on serve -> ~0.7357 game win probability
    assert game_win_prob(0.6) == pytest.approx(0.7357, abs=1e-3)
    assert game_win_prob(0.5) == pytest.approx(0.5)


def test_set_distribution_sums_to_one():
    d = set_dist(0.64, 0.6, True)
    assert sum(d.values()) == pytest.approx(1.0, abs=1e-6)


def test_equal_players_split_match_evenly():
    m = tennis_match(0.64, 0.64, 3)
    assert m["win_a"] == pytest.approx(0.5, abs=1e-9)
    assert sum(m["set_scores"].values()) == pytest.approx(1.0, abs=1e-6)
    assert sum(m["games"].values()) == pytest.approx(1.0, abs=1e-6)


def test_stronger_server_wins_more_often():
    weak = tennis_match(0.60, 0.60, 3)["win_a"]
    strong = tennis_match(0.68, 0.60, 3)["win_a"]
    assert strong > weak


def test_serve_probs_round_trip():
    pa, pb = serve_probs_for_win(0.75, base_serve=0.64, best_of=3)
    achieved = tennis_match(pa, pb, 3)["win_a"]
    assert achieved == pytest.approx(0.75, abs=1e-3)


def test_inplay_tennis_favours_leader():
    pa, pb = serve_probs_for_win(0.5, 0.64, 3)
    ahead = tennis_match(pa, pb, 3, sets=(1, 0), games_before=10, cur_games=(0, 0), cur_first_a=True)
    assert ahead["win_a"] > 0.5


def test_volleyball_equal_players():
    v = volleyball_match(0.5, 5)
    assert v["win_a"] == pytest.approx(0.5, abs=1e-9)
    assert sum(v["set_scores"].values()) == pytest.approx(1.0, abs=1e-6)


def test_rally_prob_round_trip():
    p = rally_prob_for_win(0.7, 5)
    assert volleyball_match(p, 5)["win_a"] == pytest.approx(0.7, abs=1e-3)


def test_volleyball_inplay_leader_favoured():
    p = rally_prob_for_win(0.5, 5)
    v = volleyball_match(p, 5, sets=(2, 0), cur_points=(10, 5), in_set=True)
    assert v["win_a"] > 0.5
