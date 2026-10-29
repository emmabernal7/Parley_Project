"""SofaScore public API provider for real-time live events, scores, injuries, and lineups.

Covers Soccer, Basketball, Tennis, Baseball, Hockey, American Football, Volleyball,
MMA, and Motorsport across clubs, international cups, and national tournaments.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from ...events import Event

log = logging.getLogger(__name__)

BASE_URL = "https://api.sofascore.com/api/v1"
TIMEOUT = 6.0

_client = httpx.Client(
    timeout=TIMEOUT,
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=30),
    follow_redirects=True,
)

SPORT_TO_SOFA = {
    "soccer": "football",
    "basketball": "basketball",
    "tennis": "tennis",
    "baseball": "baseball",
    "hockey": "ice-hockey",
    "american_football": "american-football",
    "volleyball": "volleyball",
    "motorsport": "motorsport",
    "mma": "mma",
}

SOFA_TO_SPORT = {v: k for k, v in SPORT_TO_SOFA.items()}


def _get(path: str) -> Optional[dict]:
    url = f"{BASE_URL}{path}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.sofascore.com",
        "Referer": "https://www.sofascore.com/",
    }
    try:
        r = _client.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()
        log.debug("SofaScore HTTP %s for %s", r.status_code, path)
    except Exception as e:
        log.debug("SofaScore request error for %s: %s", path, e)
    return None


def _status(status_code: int, status_desc: str) -> str:
    # 0 = not started, 6/7 = in progress, 100 = ended
    if status_code in (6, 7, 31, 32, 33, 34, 40, 41):
        return "live"
    if status_code in (100, 110, 120) or "Ended" in status_desc or "FT" in status_desc:
        return "finished"
    if status_code in (60, 70, 80, 90) or "Postponed" in status_desc or "Cancelled" in status_desc:
        return "postponed"
    return "scheduled"


def parse_sofa_event(ev_data: dict, default_sport: str = "soccer") -> Optional[Event]:
    try:
        ev_id = str(ev_data.get("id"))
        raw_sport = (ev_data.get("tournament", {}).get("category", {}).get("sport", {}).get("slug")
                     or default_sport)
        sport = SOFA_TO_SPORT.get(raw_sport, default_sport)

        home_team = ev_data.get("homeTeam", {}).get("name") or "Home"
        away_team = ev_data.get("awayTeam", {}).get("name") or "Away"
        tournament = ev_data.get("tournament", {})
        comp_name = tournament.get("name") or "Competition"
        cat_name = tournament.get("category", {}).get("name")
        if cat_name and cat_name not in comp_name:
            comp_name = f"{comp_name} ({cat_name})"

        ts = ev_data.get("startTimestamp")
        if ts:
            kickoff = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            kickoff = datetime.now(timezone.utc)

        st_obj = ev_data.get("status", {})
        status_code = st_obj.get("code", 0)
        status_desc = st_obj.get("description", "")
        status = _status(status_code, status_desc)

        h_score = int(ev_data.get("homeScore", {}).get("current", 0) or 0)
        a_score = int(ev_data.get("awayScore", {}).get("current", 0) or 0)

        clock: Dict[str, Any] = {}
        if status == "live":
            display_clock = st_obj.get("description") or "Live"
            clock["display"] = display_clock
            clock["minute"] = float(ev_data.get("time", {}).get("played", 0) or 0)
            if "Halftime" in display_clock or "HT" in display_clock:
                clock["phase"] = "ht"
            elif "2nd" in display_clock or clock["minute"] > 45:
                clock["phase"] = "h2"
            else:
                clock["phase"] = "h1"

        referee = ev_data.get("referee", {}).get("name")
        venue_obj = ev_data.get("venue")
        venue = None
        if venue_obj:
            venue = {
                "name": venue_obj.get("name"),
                "city": venue_obj.get("city", {}).get("name") if isinstance(venue_obj.get("city"), dict) else venue_obj.get("city"),
                "country": venue_obj.get("country", {}).get("name") if isinstance(venue_obj.get("country"), dict) else venue_obj.get("country")
            }

        meta: Dict[str, Any] = {
            "sofascore_id": ev_id,
            "has_lineups": ev_data.get("hasLineups", False),
            "tournament_slug": tournament.get("slug"),
        }

        # Manager / coaches
        home_mgr = ev_data.get("homeTeam", {}).get("manager", {}).get("name")
        away_mgr = ev_data.get("awayTeam", {}).get("manager", {}).get("name")
        if home_mgr or away_mgr:
            meta["managers"] = {"home": home_mgr, "away": away_mgr}

        return Event(
            id=f"sofa_{sport}_{ev_id}",
            sport=sport,
            competition=comp_name,
            home=home_team,
            away=away_team,
            kickoff=kickoff,
            status=status,
            score=(h_score, a_score),
            clock=clock,
            venue=venue,
            referee=referee,
            source="sofascore",
            meta=meta,
        )
    except Exception as e:
        log.debug("Error parsing SofaScore event: %s", e)
        return None


def fetch_live(sport: str) -> List[Event]:
    sofa_sport = SPORT_TO_SOFA.get(sport, sport)
    data = _get(f"/sport/{sofa_sport}/events/live")
    if not data or not isinstance(data.get("events"), list):
        return []
    out = []
    for d in data["events"]:
        ev = parse_sofa_event(d, default_sport=sport)
        if ev:
            out.append(ev)
    return out


def fetch_scheduled(sport: str, days_ahead: int = 2) -> List[Event]:
    sofa_sport = SPORT_TO_SOFA.get(sport, sport)
    events: List[Event] = []
    seen = set()
    today = datetime.now(timezone.utc)

    for offset in range(0, min(days_ahead + 1, 3)):
        date_str = (today + timedelta(days=offset)).strftime("%Y-%m-%d")
        data = _get(f"/sport/{sofa_sport}/scheduled-events/{date_str}")
        if not data or not isinstance(data.get("events"), list):
            continue
        for d in data["events"]:
            ev = parse_sofa_event(d, default_sport=sport)
            if ev and ev.id not in seen:
                seen.add(ev.id)
                events.append(ev)
    return events


def fetch_lineups_and_injuries(event_id: str) -> Dict[str, Any]:
    """Fetches missing players, injuries, starting players and coaches for an event."""
    data = _get(f"/event/{event_id}/lineups")
    if not data:
        return {}
    out: Dict[str, Any] = {"injuries": [], "home_starters": [], "away_starters": []}
    missing = data.get("missingPlayers", {})
    for side in ("home", "away"):
        for p in missing.get(side, []):
            player = p.get("player", {})
            reason = p.get("reason", "Out")
            out["injuries"].append({
                "side": side,
                "player": player.get("name"),
                "position": player.get("position"),
                "reason": reason,
            })
    return out


def fetch(sport: str, days_ahead: int = 2) -> List[Event]:
    """Combines live and upcoming matches for the requested sport."""
    events: List[Event] = []
    seen = set()

    # 1. Live events first
    for ev in fetch_live(sport):
        if ev.id not in seen:
            seen.add(ev.id)
            events.append(ev)

    # 2. Scheduled events
    for ev in fetch_scheduled(sport, days_ahead=days_ahead):
        if ev.id not in seen:
            seen.add(ev.id)
            events.append(ev)

    return events
