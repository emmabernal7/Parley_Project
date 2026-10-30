import os
import tempfile

import pytest


@pytest.fixture()
def client():
    os.environ["SQ_DB"] = os.path.join(tempfile.mkdtemp(), "api_test.db")
    from datetime import datetime, timezone
    from fastapi.testclient import TestClient
    from sportsquant.events import Event
    from sportsquant.web.app import app, state
    with TestClient(app) as c:
        mock_ev = Event(
            id="test_ev_1", sport="soccer", competition="La Liga",
            home="Barcelona", away="Real Madrid", kickoff=datetime.now(timezone.utc),
            status="scheduled", score=(0, 0), source="test"
        )
        state["live"].events[mock_ev.id] = mock_ev
        yield c


def test_index_and_settings(client):
    assert client.get("/").status_code == 200
    r = client.get("/api/settings")
    assert r.status_code == 200 and "bankroll" in r.json()


def test_events_and_detail_roundtrip(client):
    evs = client.get("/api/events").json()
    assert len(evs) > 0
    eid = [e for e in evs if e["sport"] == "soccer"][0]["id"]
    detail = client.get(f"/api/event/{eid}").json()
    assert "groups" in detail and len(detail["groups"]) > 0
    gids = {g["id"] for g in detail["groups"]}
    assert "1x2" in gids or "ml" in gids


def test_unknown_event_404s(client):
    assert client.get("/api/event/does-not-exist").status_code == 404


def test_user_odds_roundtrip_and_value_flow(client):
    evs = client.get("/api/events").json()
    eid = [e for e in evs if e["sport"] == "soccer"][0]["id"]
    detail = client.get(f"/api/event/{eid}").json()
    g1x2 = next(g for g in detail["groups"] if g["id"] == "1x2")
    sel = g1x2["selections"][0]
    r = client.post(f"/api/event/{eid}/odds", json={"key": f"1x2:{sel['id']}", "odds": sel["odds"] * 1.2})
    assert r.status_code == 200
    detail2 = client.get(f"/api/event/{eid}").json()
    g2 = next(g for g in detail2["groups"] if g["id"] == "1x2")
    assert g2["selections"][0].get("user_odds") == pytest.approx(sel["odds"] * 1.2)


def test_chat_offline_reply(client):
    r = client.post("/api/chat", json={"session_id": "t1", "message": "hello"})
    assert r.status_code == 200 and len(r.json()["reply"]) > 0


def test_chat_proposition_query(client):
    queries = [
        "what does it think about an Over 3.5 runs by Tampa Bay for example",
        "Over 3.5 runs Tampa Bay vs Guardians",
        "que opinas de over 3.5 carreras de tampa bay",
    ]
    for q in queries:
        r = client.post("/api/chat", json={"session_id": "t_prop", "message": q})
        assert r.status_code == 200
        reply = r.json()["reply"]
        assert "%" in reply
        assert "Tampa Bay" in reply
        assert "Kelly" in reply or "banca" in reply.lower()


def test_slip_and_paper_bet_flow(client):
    evs = client.get("/api/events").json()
    eid = [e for e in evs if e["sport"] == "soccer"][0]["id"]
    detail = client.get(f"/api/event/{eid}").json()
    g1x2 = next(g for g in detail["groups"] if g["id"] == "1x2")
    key = f"1x2:{g1x2['selections'][0]['id']}"

    r = client.post("/api/slip/add", json={"session_id": "t2", "event_id": eid, "key": key})
    assert len(r.json()["slip"]) == 1

    r = client.get("/api/slip", params={"session_id": "t2"})
    assert r.json()["priced"]["fair_parlay_odds"] > 1

    r = client.post("/api/bets", json={"session_id": "t2", "stake": 5})
    assert r.status_code == 200
    bet_id = r.json()["id"]

    bets = client.get("/api/bets").json()
    assert any(b["id"] == bet_id for b in bets)

    assert client.get("/api/slip", params={"session_id": "t2"}).json()["legs"] == []
    assert client.delete(f"/api/bets/{bet_id}").status_code == 200

    # Bankroll endpoint summary test
    bankroll = client.get("/api/bankroll").json()
    assert "current_bankroll" in bankroll
    assert "settled_pnl" in bankroll
    assert "open_stake" in bankroll

    # Clear all bets test
    assert client.delete("/api/bets").status_code == 200
    assert len(client.get("/api/bets").json()) == 0


def test_data_status_and_social_status(client):
    assert client.get("/api/data-status").status_code == 200
    r = client.get("/api/social/status").json()
    assert r["enabled"] is False
