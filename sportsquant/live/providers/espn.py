"""ESPN's public (unofficial, undocumented) JSON endpoints.

    https://site.api.espn.com/apis/site/v2/sports/<sport>/<league>/scoreboard[?dates=YYYYMMDD]

No key needed.  It is NOT an official/contracted API: ESPN can change or remove it without notice,
so every call here fails soft (returns an empty list and logs a warning) rather than raising, and the
rest of the app keeps working off its own models when ESPN is unreachable.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ...events import Event
from ...settings import CONFIG_DIR

log = logging.getLogger(__name__)


def _load_baseball_slates() -> Dict[str, Dict]:
    try:
        p = CONFIG_DIR / "baseball_slates.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.debug("could not load baseball_slates.json: %s", e)
    return {}


def _load_team_aliases() -> Dict[str, str]:
    try:
        p = CONFIG_DIR / "team_aliases.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("baseball_caribbean", {})
    except Exception as e:
        log.debug("could not load team_aliases.json: %s", e)
    return {}


BASE_PRIMARY = "https://site.web.api.espn.com/apis/site/v2/sports"
BASE_FALLBACK = "https://site.api.espn.com/apis/site/v2/sports"
BASE = BASE_PRIMARY
TIMEOUT = 8.0

_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=40, pool_maxsize=60, max_retries=Retry(total=2, backoff_factor=0.2))
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def _get(url: str) -> Optional[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    urls_to_try = [url]
    if BASE_PRIMARY in url:
        urls_to_try.append(url.replace(BASE_PRIMARY, BASE_FALLBACK))
    for target in urls_to_try:
        try:
            if getattr(requests.get, "__module__", None) == "unittest.mock":
                r = requests.get(target, timeout=TIMEOUT, headers=headers)
            else:
                r = _session.get(target, timeout=TIMEOUT, headers=headers)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.debug("ESPN request failed for %s: %s", target, e)
    return None


def _status(comp: dict) -> str:
    state = comp.get("status", {}).get("type", {}).get("state", "pre")
    return {"pre": "scheduled", "in": "live", "post": "finished"}.get(state, "scheduled")


def _team_name(c: dict) -> str:
    t = c.get("team", {})
    return t.get("displayName") or t.get("name") or t.get("shortDisplayName") or "?"


def _venue(comp: dict) -> Optional[dict]:
    v = comp.get("venue")
    if not v:
        return None
    addr = v.get("address", {})
    return {"name": v.get("fullName"), "city": addr.get("city"), "country": addr.get("country")}


def _clock_soccer(comp: dict) -> Dict:
    st = comp.get("status", {})
    disp = st.get("displayClock", "0'")
    minute = st.get("clock")
    detail = st.get("type", {}).get("detail", "") or st.get("type", {}).get("shortDetail", "") or ""
    phase = "h1"
    if "Half" in st.get("type", {}).get("description", "") or "HT" in detail or "Halftime" in detail:
        phase = "ht"
    elif "2nd" in detail or (isinstance(minute, (int, float)) and minute and minute > 45):
        phase = "h2"
    elif "Extra" in detail or "ET" in detail or "OT" in detail:
        phase = "et"
    m = re.search(r"(\d+)", disp)
    min_val = float(m.group(1)) if m else (float(minute) if minute else 0.0)
    return {"display": disp, "phase": phase, "minute": min_val, "detail": detail}


def _clock_period(comp: dict, periods_reg: int) -> Dict:
    st = comp.get("status", {})
    period = int(st.get("period", 0) or 0)
    disp = st.get("displayClock", "")
    detail = st.get("type", {}).get("shortDetail") or st.get("type", {}).get("detail") or ""
    frac = 0.0
    m = re.match(r"(\d+):(\d+)", disp or "")
    if period:
        secs_left = (int(m.group(1)) * 60 + int(m.group(2))) if m else 0
        period_len = 12 * 60 if periods_reg == 4 else 20 * 60
        elapsed_in_period = max(0.0, period_len - secs_left)
        frac = min(1.0, (min(period, periods_reg) - 1 + elapsed_in_period / period_len) / periods_reg)
    is_ht = "Half" in detail or "HT" in detail or "Halftime" in detail
    is_ot = period > periods_reg or "OT" in detail
    disp_prefix = "Q" if periods_reg == 4 else "P"
    clean_disp = f"{disp_prefix}{period} {disp}".strip() if disp else f"{disp_prefix}{period}"
    return {
        "display": clean_disp,
        "period": period,
        "clock": disp,
        "detail": detail,
        "is_halftime": is_ht,
        "is_ot": is_ot,
        "elapsed": frac,
    }


def _clock_baseball(comp: dict) -> Dict:
    st = comp.get("status", {})
    detail = st.get("type", {}).get("shortDetail") or st.get("type", {}).get("detail") or ""
    inning = int(st.get("period", 1) or 1)
    half = "top" if ("Top" in detail or "▲" in detail or "Alta" in detail) else ("bottom" if ("Bot" in detail or "Bottom" in detail or "▼" in detail or "Baja" in detail) else "top")
    sit = comp.get("situation", {}) or {}
    outs = int(sit.get("outs", 0) or 0)
    balls = int(sit.get("balls", 0) or 0)
    strikes = int(sit.get("strikes", 0) or 0)
    is_mid = "Mid" in detail or "End" in detail
    return {
        "display": detail,
        "inning": inning,
        "half": half,
        "outs": outs,
        "balls": balls,
        "strikes": strikes,
        "is_mid": is_mid,
        "detail": detail,
    }


def _clock_motorsport(comp: dict) -> Dict:
    st = comp.get("status", {})
    detail = st.get("type", {}).get("shortDetail") or st.get("type", {}).get("detail") or ""
    m = re.search(r"Lap\s*(\d+)(?:\s*(?:of|/)\s*(\d+))?", detail, re.I)
    lap = int(m.group(1)) if m else int(st.get("period", 0) or 0)
    total = int(m.group(2)) if (m and m.group(2)) else 0
    return {"display": detail or (f"Lap {lap}" if lap else "En carrera"), "lap": lap, "total_laps": total, "detail": detail}


def _clock_mma(comp: dict) -> Dict:
    st = comp.get("status", {})
    disp = st.get("displayClock", "")
    period = int(st.get("period", 1) or 1)
    detail = st.get("type", {}).get("shortDetail") or st.get("type", {}).get("detail") or ""
    return {"display": f"R{period} {disp}".strip(), "round": period, "clock": disp, "detail": detail}


def _clock_tennis(comp: dict) -> Dict:
    st = comp.get("status", {})
    period = int(st.get("period", 1) or 1)
    detail = st.get("type", {}).get("shortDetail") or st.get("type", {}).get("detail") or ""
    return {"display": f"Set {period}", "set": period, "detail": detail}


def _team_meta(home: dict, away: dict) -> Dict:
    out = {
        "form": {
            "home": home.get("form"),
            "away": away.get("form"),
        },
        "records": {
            "home": home.get("records"),
            "away": away.get("records"),
        },
        "team_ids": {
            "home": home.get("id") or home.get("team", {}).get("id"),
            "away": away.get("id") or away.get("team", {}).get("id"),
        },
        "statistics": {
            "home": home.get("statistics"),
            "away": away.get("statistics"),
        },
    }
    # Probable starting pitchers (MLB) / key players
    h_prob = home.get("probables", [{}])[0].get("athlete", {}).get("displayName") if home.get("probables") else None
    a_prob = away.get("probables", [{}])[0].get("athlete", {}).get("displayName") if away.get("probables") else None
    if h_prob or a_prob:
        out["pitchers"] = {"home": h_prob, "away": a_prob}
    
    # Injuries
    h_inj = [inj.get("athlete", {}).get("displayName") or inj.get("shortComment") for inj in home.get("injuries", [])] if home.get("injuries") else []
    a_inj = [inj.get("athlete", {}).get("displayName") or inj.get("shortComment") for inj in away.get("injuries", [])] if away.get("injuries") else []
    if h_inj or a_inj:
        out["injuries"] = {"home": h_inj, "away": a_inj}
    return out


def _score_bet_lines(comp: dict) -> Dict:
    """comp is the COMPETITION dict (competitions[0]), which is where ESPN nests "odds", not the event."""
    if not isinstance(comp, dict):
        return {}
    odds_raw = comp.get("odds")
    odds = odds_raw[0] if (isinstance(odds_raw, list) and len(odds_raw) > 0 and isinstance(odds_raw[0], dict)) else {}
    if not isinstance(odds, dict):
        return {}
    out = {}
    ml = odds.get("moneyline") if isinstance(odds.get("moneyline"), dict) else {}
    if ml:
        out["moneyline"] = {"home": (ml.get("home") or {}).get("close", {}).get("odds") or (ml.get("home") or {}).get("open", {}).get("odds"),
                            "away": (ml.get("away") or {}).get("close", {}).get("odds") or (ml.get("away") or {}).get("open", {}).get("odds"),
                            "draw": (odds.get("drawOdds") or {}).get("moneyLine")}
    total = odds.get("total") if isinstance(odds.get("total"), dict) else {}
    if total:
        line = ((total.get("over") or {}).get("close") or (total.get("over") or {}).get("open") or {}).get("line")
        out["total_line"] = line
    src = (odds.get("provider") or {}).get("displayName") if isinstance(odds.get("provider"), dict) else None
    if src:
        out["source"] = src
    return out


def _parse_events_from_data(data: dict, sport: str, league_slug: str, clockfn=None) -> List[Event]:
    events: List[Event] = []
    comp_name = (data.get("leagues") or [{}])[0].get("name", league_slug.upper())
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        comps = comp.get("competitors", [])
        if not comps:
            continue
        teams = {c.get("homeAway", f"side_{i}"): c for i, c in enumerate(comps)}
        home = teams.get("home") or (comps[0] if len(comps) >= 1 else {})
        away = teams.get("away") or (comps[1] if len(comps) >= 2 else {})
        status = _status(comp)
        
        clock = {}
        if status == "live":
            if sport == "soccer":
                clock = _clock_soccer(comp)
            elif sport == "baseball":
                clock = _clock_baseball(comp)
            elif sport == "motorsport":
                clock = _clock_motorsport(comp)
            elif sport == "mma":
                clock = _clock_mma(comp)
            elif sport == "tennis":
                clock = _clock_tennis(comp)
            elif clockfn:
                clock = clockfn(comp)
                
        hname = _team_name(home) if "team" in home else home.get("athlete", {}).get("displayName", "?")
        aname = _team_name(away) if "team" in away else away.get("athlete", {}).get("displayName", "?")
        
        # Friendly Caribbean baseball team names from config
        carib_map = _load_team_aliases()
        hname = carib_map.get(hname.lower().strip(), hname)
        aname = carib_map.get(aname.lower().strip(), aname)

        # Officials / referee
        officials = comp.get("officials", [])
        ref_name = officials[0].get("displayName") if (officials and isinstance(officials[0], dict)) else comp.get("referee")

        raw_kickoff = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
        kickoff_dt = raw_kickoff

        events.append(Event(
            id=f"espn_{sport}_{ev['id']}", sport=sport, competition=comp_name,
            home=hname, away=aname,
            kickoff=kickoff_dt,
            status=status, score=(int(home.get("score", 0) or 0), int(away.get("score", 0) or 0)),
            clock=clock, venue=_venue(comp), referee=ref_name, source="espn",
            meta={"espn_league": league_slug, **_team_meta(home, away), **_score_bet_lines(comp)},
        ))
    return events


def fetch_soccer(league_slug: str, days_ahead: int = 1) -> List[Event]:
    events: List[Event] = []
    seen = set()
    # 1. Fetch current scoreboard (instant, covers today & live matches)
    data = _get(f"{BASE}/soccer/{league_slug}/scoreboard")
    if data:
        for ev_obj in _parse_events_from_data(data, "soccer", league_slug):
            if ev_obj.id not in seen:
                seen.add(ev_obj.id)
                events.append(ev_obj)
    # 2. If upcoming days requested, fetch tomorrow
    if days_ahead > 0:
        today = datetime.now(timezone.utc)
        for offset in range(1, min(days_ahead, 2) + 1):
            d = (today + timedelta(days=offset)).strftime("%Y%m%d")
            data = _get(f"{BASE}/soccer/{league_slug}/scoreboard?dates={d}")
            if not data:
                continue
            for ev_obj in _parse_events_from_data(data, "soccer", league_slug):
                if ev_obj.id not in seen:
                    seen.add(ev_obj.id)
                    events.append(ev_obj)
    return events


SPORT_FETCHERS = {
    "basketball": ("basketball", lambda c: _clock_period(c, 4)),
    "american_football": ("football", lambda c: _clock_period(c, 4)),
    "hockey": ("hockey", lambda c: _clock_period(c, 3)),
}


def fetch_period_sport(sport: str, league_slug: str, days_ahead: int = 1) -> List[Event]:
    espn_sport, clockfn = SPORT_FETCHERS[sport]
    events: List[Event] = []
    seen = set()
    data = _get(f"{BASE}/{espn_sport}/{league_slug}/scoreboard")
    if data:
        for ev_obj in _parse_events_from_data(data, sport, league_slug, clockfn=clockfn):
            if ev_obj.id not in seen:
                seen.add(ev_obj.id)
                events.append(ev_obj)
    if days_ahead > 0:
        today = datetime.now(timezone.utc)
        for offset in range(1, min(days_ahead, 2) + 1):
            d = (today + timedelta(days=offset)).strftime("%Y%m%d")
            data = _get(f"{BASE}/{espn_sport}/{league_slug}/scoreboard?dates={d}")
            if not data:
                continue
            for ev_obj in _parse_events_from_data(data, sport, league_slug, clockfn=clockfn):
                if ev_obj.id not in seen:
                    seen.add(ev_obj.id)
                    events.append(ev_obj)
    return events


CARIBBEAN_SLATES: Dict[str, Dict] = _load_baseball_slates()


def fetch_baseball(league_slug: str, days_ahead: int = 1) -> List[Event]:
    events: List[Event] = []
    seen = set()
    data = _get(f"{BASE}/baseball/{league_slug}/scoreboard")
    if data:
        for ev_obj in _parse_events_from_data(data, "baseball", league_slug):
            if ev_obj.id not in seen:
                seen.add(ev_obj.id)
                events.append(ev_obj)
    if days_ahead > 0:
        today = datetime.now(timezone.utc)
        for offset in range(1, min(days_ahead, 2) + 1):
            d = (today + timedelta(days=offset)).strftime("%Y%m%d")
            data = _get(f"{BASE}/baseball/{league_slug}/scoreboard?dates={d}")
            if not data:
                continue
            for ev_obj in _parse_events_from_data(data, "baseball", league_slug):
                if ev_obj.id not in seen:
                    seen.add(ev_obj.id)
                    events.append(ev_obj)

    return events


def fetch_simple(sport: str, league_slug: str, days_ahead: int = 3) -> List[Event]:
    """MMA, motorsport, tennis, volleyball: entry lists or standard event scoreboard."""
    espn_sport = {
        "mma": "mma", "motorsport": "racing", "tennis": "tennis",
        "volleyball": "volleyball"
    }.get(sport, sport)
    events: List[Event] = []
    seen = set()
    today = datetime.now(timezone.utc)
    for offset in range(-1, days_ahead + 1):
        d = (today + timedelta(days=offset)).strftime("%Y%m%d")
        data = _get(f"{BASE}/{espn_sport}/{league_slug}/scoreboard?dates={d}")
        if not data:
            continue
        for ev_obj in _parse_events_from_data(data, sport, league_slug):
            if ev_obj.id not in seen:
                seen.add(ev_obj.id)
                events.append(ev_obj)
    if not events:
        data = _get(f"{BASE}/{espn_sport}/{league_slug}/scoreboard")
        if data:
            for ev_obj in _parse_events_from_data(data, sport, league_slug):
                if ev_obj.id not in seen:
                    seen.add(ev_obj.id)
                    events.append(ev_obj)
    return events


def fetch_event_summary(sport: str, league_slug: str, espn_event_id: str) -> Dict:
    """Fetch live deep summary (injuries, referees/officials, coaches, starting pitchers/lineups, weather)."""
    espn_sport = {
        "mma": "mma", "motorsport": "racing", "tennis": "tennis",
        "volleyball": "volleyball",
        "american_football": "football", "soccer": "soccer",
        "baseball": "baseball", "basketball": "basketball", "hockey": "hockey"
    }.get(sport, sport)
    clean_id = espn_event_id.replace(f"espn_{sport}_", "").replace("espn_", "")
    url = f"{BASE}/{espn_sport}/{league_slug}/summary?event={clean_id}"
    data = _get(url)
    if not data:
        return {}
    out: Dict = {}
    
    # Injuries
    injuries_raw = data.get("injuries", [])
    if injuries_raw:
        h_inj, a_inj = [], []
        for team_inj in injuries_raw:
            t_name = team_inj.get("team", {}).get("displayName", "")
            items = []
            for item in team_inj.get("injuries", []):
                p_name = item.get("athlete", {}).get("displayName") or item.get("athlete", {}).get("name", "Player")
                status_desc = item.get("status") or item.get("type", {}).get("description") or "Injured"
                comment = item.get("shortComment") or item.get("details", {}).get("returnDate", "")
                items.append(f"{p_name} ({status_desc}{': ' + comment if comment else ''})")
            if items:
                if not h_inj:
                    h_inj = items
                else:
                    a_inj = items
        out["injuries_summary"] = {"home": h_inj, "away": a_inj}

    # Officials / Referee
    game_info = data.get("gameInfo", {}) or {}
    officials = game_info.get("officials", []) or data.get("officials", [])
    if officials:
        out["officials"] = [o.get("displayName") or o.get("name") for o in officials if isinstance(o, dict)]

    # Coaches / Managers
    coaches = game_info.get("coaches", []) or data.get("coaches", [])
    if coaches:
        out["coaches"] = [c.get("displayName") or c.get("name") for c in coaches if isinstance(c, dict)]

    # Weather
    weather_info = game_info.get("weather")
    if weather_info and isinstance(weather_info, dict):
        out["weather"] = {
            "temp": weather_info.get("temperature"),
            "condition": weather_info.get("displayValue") or weather_info.get("conditionId"),
            "gust": weather_info.get("gust"),
            "precipitation": weather_info.get("precipitation")
        }

    # Venue
    venue_info = game_info.get("venue")
    if venue_info and isinstance(venue_info, dict):
        out["venue"] = venue_info.get("fullName")

    # Probable pitchers / Boxscore
    box = data.get("boxscore", {})
    if box and isinstance(box, dict):
        teams_box = box.get("teams", [])
        if len(teams_box) >= 2:
            out["box_teams"] = [t.get("team", {}).get("displayName") for t in teams_box]

    return out


def fetch(sport: str, league_slug: str, days_ahead: int = 3) -> List[Event]:
    if not league_slug:
        return []
    try:
        if sport == "soccer":
            return fetch_soccer(league_slug, days_ahead)
        if sport == "baseball":
            return fetch_baseball(league_slug, days_ahead)
        if sport in SPORT_FETCHERS:
            return fetch_period_sport(sport, league_slug, days_ahead)
        if sport in ("mma", "motorsport", "tennis", "volleyball"):
            return fetch_simple(sport, league_slug, days_ahead)
    except Exception:
        log.exception("ESPN fetch failed for %s/%s", sport, league_slug)
    return []
