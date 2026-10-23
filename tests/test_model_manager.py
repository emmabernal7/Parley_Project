from datetime import datetime, timezone

from sportsquant.data.synthetic import simulate_soccer_league
from sportsquant.events import Event
from sportsquant.services.model_manager import ModelManager

TEAMS = ["Barcelona", "Real Madrid", "Atletico Madrid", "Sevilla", "Villarreal", "Real Sociedad",
        "Athletic Bilbao", "Valencia", "Real Betis", "Girona", "Celta Vigo", "Osasuna", "Getafe",
        "Mallorca", "Las Palmas", "Rayo Vallecano", "Alaves", "Cadiz", "Almeria", "Granada"]


def _seeded_manager(tmp_store):
    df, _ = simulate_soccer_league(TEAMS, seasons=3, seed=7, referees=[f"Ref{i}" for i in range(10)])
    df["league"] = "ESP1"
    df["match_id"] = [f"sim_{i}" for i in range(len(df))]
    tmp_store.save_matches(df)
    mm = ModelManager(tmp_store)
    mm.refit()
    return mm


def _ev(home, away, competition="La Liga"):
    return Event(id="x", sport="soccer", competition=competition, home=home, away=away,
                kickoff=datetime.now(timezone.utc))


def test_fitted_league_gives_ok_confidence(tmp_store):
    mm = _seeded_manager(tmp_store)
    pr = mm.soccer_pricer(_ev("Barcelona", "Villarreal"))
    assert pr.confidence == "ok"
    assert "Dixon-Coles fitted" in pr.model_label


def test_fuzzy_name_matching_resolves_typos(tmp_store):
    mm = _seeded_manager(tmp_store)
    pr = mm.soccer_pricer(_ev("FC Barcelona", "Villareal"))  # extra "FC", missing "r"
    assert pr.confidence == "ok"


def test_unknown_competition_falls_back_honestly(tmp_store):
    mm = _seeded_manager(tmp_store)
    pr = mm.soccer_pricer(_ev("Team Zed", "Team Yak", competition="Unknown Cup"))
    assert pr.confidence == "ok"
    assert "cálculo híbrido" in pr.model_label.lower()


def test_hybrid_model_with_espn_form_and_records(tmp_store):
    mm = ModelManager(tmp_store)
    ev = _ev("Getafe", "Malaga", competition="Copa del Rey")
    ev.meta = {
        "form": {"home": "WWWDW", "away": "LLDLL"},
        "records": {
            "home": [{"name": "All Splits", "type": "total", "summary": "10-2-1"}],
            "away": [{"name": "All Splits", "type": "total", "summary": "1-3-9"}]
        }
    }
    pr = mm.soccer_pricer(ev)
    assert pr.confidence == "ok"
    assert "cálculo híbrido" in pr.model_label.lower()
    # Getafe with WWWDW form and strong record should have higher lambda than Malaga's mu
    assert pr.lam > pr.mu


def test_demo_event_is_labelled_demo(tmp_store):
    mm = ModelManager(tmp_store)
    ev = _ev("Barcelona", "Galatasaray")
    ev.source = "demo"
    ev.meta = {"lam": 2.3, "mu": 0.7, "rho": -0.08}
    pr = mm.soccer_pricer(ev)
    assert pr.confidence == "demo"

