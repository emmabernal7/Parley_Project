import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sportsquant.ingest.footballdata import FootballDataIngester
from sportsquant.live.providers import espn

FIXTURES = Path(__file__).parent / "fixtures"


def test_footballdata_parses_real_column_layout(tmp_store):
    ing = FootballDataIngester(tmp_store)
    text = (FIXTURES / "E0_sample.csv").read_text(encoding="latin-1")
    matches, odds = ing.parse(text, "E0", "2023-2024")
    assert len(matches) == 8
    assert set(matches["league"]) == {"ENG1"}
    assert matches["referee"].notna().any()
    assert matches["hc"].notna().any() and matches["hy"].notna().any()
    assert len(odds) > 0
    assert "1X2_close" in odds["market"].unique()


def test_footballdata_season_code_formats():
    assert FootballDataIngester.season_code("2023-2024") == "2324"
    assert FootballDataIngester.season_code("2023/24") == "2324"
    assert FootballDataIngester.season_code("2324") == "2324"
    with pytest.raises(ValueError):
        FootballDataIngester.season_code("garbage")


def test_footballdata_save_and_load_roundtrip(tmp_store):
    ing = FootballDataIngester(tmp_store)
    text = (FIXTURES / "E0_sample.csv").read_text(encoding="latin-1")
    matches, odds = ing.parse(text, "E0", "2023-2024")
    ing._save(matches, odds)
    loaded = tmp_store.load_matches()
    assert len(loaded) == 8
    assert tmp_store.match_counts() == {"ENG1": 8}


def test_espn_bet_lines_read_from_competition_not_event():
    data = json.loads((FIXTURES / "espn_soccer_sample.json").read_text())
    comp = data["events"][0]["competitions"][0]
    lines = espn._score_bet_lines(comp)
    assert lines["moneyline"]["home"] == "+175"
    assert lines["moneyline"]["draw"] == 280
    assert lines["source"] == "DraftKings"


def test_espn_fetch_soccer_end_to_end_with_mocked_http():
    data = json.loads((FIXTURES / "espn_soccer_sample.json").read_text())
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    with patch("sportsquant.live.providers.espn.requests.get", return_value=resp):
        events = espn.fetch("soccer", "eng.1", days_ahead=0)
    assert len(events) == 1
    assert events[0].home == "Brentford" and events[0].away == "Chelsea"
    assert events[0].status == "scheduled"


def test_espn_fetch_fails_soft_on_network_error():
    import requests
    with patch("sportsquant.live.providers.espn.requests.get", side_effect=requests.ConnectionError("no network")):
        events = espn.fetch("soccer", "eng.1", days_ahead=0)
    assert events == []
