"""TheSportsDB public free REST API provider.

    https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d=YYYY-MM-DD

No API key needed (uses public key '3'). Provides fixtures, scores, and events across
Soccer, Basketball, American Football, Baseball, Ice Hockey, Tennis, Motorsport, and MMA.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

from ...events import Event

log = logging.getLogger(__name__)

BASE_URL = "https://www.thesportsdb.com/api/v1/json/123"
TIMEOUT = 8

SPORT_MAP = {
    "Soccer": "soccer",
    "Basketball": "basketball",
    "American Football": "american_football",
    "Baseball": "baseball",
    "Ice Hockey": "hockey",
    "Hockey": "hockey",
    "Tennis": "tennis",
    "Motorsport": "motorsport",
    "Formula 1": "motorsport",
    "Fighting": "mma",
    "MMA": "mma",
    "Mixed Martial Arts": "mma",
    "Volleyball": "volleyball",
    "Waterpolo": "waterpolo",
    "Water Polo": "waterpolo",
}

LEAGUE_IDS = {
    "soccer": ["4328", "4329", "4330", "4331", "4332", "4333", "4334", "4335", "4336", "4346", "4424", "4351", "4480", "4481", "4482"],  # Leagues + FA Cup, Copa del Rey, DFB-Pokal, Coppa Italia, UCL, UEL, Copa Libertadores
    "basketball": ["4387", "4388", "4408", "4409"],  # NBA, NCAA Basketball, EuroLeague, ACB
    "american_football": ["4391", "4479"],  # NFL, NCAA Football
    "baseball": ["4424", "4427"],  # MLB
    "hockey": ["4380"],  # NHL
    "tennis": ["4464"],
    "motorsport": ["4370"],  # F1
    "mma": ["4443"],  # UFC
    "volleyball": ["4974"],  # Volleyball
    "waterpolo": ["5211"],  # Water Polo
}


def _get(url: str) -> Optional[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    try:
        r = requests.get(url, timeout=TIMEOUT, headers=headers)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        log.debug("TheSportsDB request failed for %s: %s", url, e)
        return None


def fetch(sport: str, days_ahead: int = 3) -> List[Event]:
    events: List[Event] = []
    today = datetime.now(timezone.utc)
    seen = set()

    for offset in range(0, days_ahead + 1):
        date_str = (today + timedelta(days=offset)).strftime("%Y-%m-%d")
        url = f"{BASE_URL}/eventsday.php?d={date_str}"
        data = _get(url)
        if not data or not isinstance(data.get("events"), list):
            continue

        for item in data["events"]:
            raw_sport = item.get("strSport") or ""
            mapped_sport = SPORT_MAP.get(raw_sport, raw_sport.lower())
            if sport and mapped_sport != sport:
                continue

            ev_id = f"tsdb_{item.get('idEvent')}"
            if ev_id in seen:
                continue

            home = item.get("strHomeTeam") or "?"
            away = item.get("strAwayTeam") or "?"
            comp = item.get("strLeague") or "TheSportsDB Event"
            date_time_str = f"{item.get('dateEvent', date_str)}T{item.get('strTime', '00:00:00')}"
            
            try:
                kickoff = datetime.fromisoformat(date_time_str.replace("Z", "+00:00"))
                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=timezone.utc)
            except Exception:
                kickoff = today

            h_score = int(item.get("intHomeScore") or 0) if item.get("intHomeScore") is not None else 0
            a_score = int(item.get("intAwayScore") or 0) if item.get("intAwayScore") is not None else 0
            
            status_str = (item.get("strStatus") or "").lower()
            if "ft" in status_str or "post" in status_str or "finish" in status_str:
                status = "finished"
            elif "in" in status_str or "live" in status_str:
                status = "live"
            else:
                status = "scheduled"

            seen.add(ev_id)
            events.append(Event(
                id=ev_id,
                sport=mapped_sport,
                competition=comp,
                home=home,
                away=away,
                kickoff=kickoff,
                status=status,
                score=(h_score, a_score),
                source="thesportsdb",
                meta={"tsdb_id": item.get("idEvent")}
            ))

    return events
