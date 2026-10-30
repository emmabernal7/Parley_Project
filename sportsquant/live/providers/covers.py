"""Covers.com Consensus Scraper & Cache Provider.
Extracts public betting consensus percentages, lines, and contest picks
from Covers.com without requiring external API keys.
Includes a thread-safe in-memory cache (TTL: 15 minutes) and fail-soft handling.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

COVERS_BASE_URL = "https://contests.covers.com/consensus/topconsensus"
CACHE_TTL_SECONDS = 900.0  # 15 minutes

_CACHE: Dict[str, List[Dict]] = {}
_CACHE_TIME: Dict[str, float] = {}
_LOCK = threading.Lock()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}

LEAGUE_SPORT_MAP = {
    "nba": "basketball",
    "ncaab": "basketball",
    "wnba": "basketball",
    "nhl": "hockey",
    "nfl": "american_football",
    "ncaaf": "american_football",
    "mlb": "baseball",
    "soccer": "soccer",
}


def _clean_pct(text: str) -> Optional[int]:
    m = re.search(r"(\d+)\s*%", text)
    return int(m.group(1)) if m else None


def parse_covers_html(html: str) -> List[Dict]:
    """Parse Covers.com consensus table into structured list."""
    out: List[Dict] = []
    if not html:
        return out

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return out

    tbody = table.find("tbody")
    if not tbody:
        return out

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue

        c0, c1, c2, c3, c4 = tds[:5]

        # Matchup info
        lg_el = c0.find(class_="covers-CoversConsensus-table--league")
        league = lg_el.get_text(strip=True).upper() if lg_el else ""

        tb1 = c0.find(class_="covers-CoversConsensus-table--teamBlock")
        tb2 = c0.find(class_="covers-CoversConsensus-table--teamBlock2")

        team1 = ""
        team2 = ""
        if tb1:
            a_el = tb1.find("a")
            team1 = a_el.get("title", tb1.get_text(strip=True)) if a_el else tb1.get_text(strip=True)
        if tb2:
            a_el = tb2.find("a")
            team2 = a_el.get("title", tb2.get_text(strip=True)) if a_el else tb2.get_text(strip=True)

        if not team1 or not team2:
            continue

        # Date / Time
        date_str = " ".join(c1.stripped_strings)

        # Consensus percentages
        pct_strs = list(c2.stripped_strings)
        pct1 = _clean_pct(pct_strs[0]) if len(pct_strs) > 0 else None
        pct2 = _clean_pct(pct_strs[1]) if len(pct_strs) > 1 else None

        # Lines / Sides
        line_strs = list(c3.stripped_strings)
        line1 = line_strs[0] if len(line_strs) > 0 else ""
        line2 = line_strs[1] if len(line_strs) > 1 else ""

        # Picks count
        picks_strs = list(c4.stripped_strings)
        picks1 = picks_strs[0] if len(picks_strs) > 0 else "0"
        picks2 = picks_strs[1] if len(picks_strs) > 1 else "0"

        # Determine favored & underdog side
        fav_team, fav_pct, dog_team, dog_pct = "", 0, "", 0
        if pct1 is not None and pct2 is not None:
            if pct1 >= pct2:
                fav_team, fav_pct = team1, pct1
                dog_team, dog_pct = team2, pct2
            else:
                fav_team, fav_pct = team2, pct2
                dog_team, dog_pct = team1, pct1

        sport = LEAGUE_SPORT_MAP.get(league.lower(), "other")

        out.append({
            "league": league,
            "sport": sport,
            "matchup": f"{team1} vs {team2}",
            "date": date_str,
            "team1": team1,
            "team2": team2,
            "pct1": pct1 or 0,
            "pct2": pct2 or 0,
            "line1": line1,
            "line2": line2,
            "picks1": picks1,
            "picks2": picks2,
            "favored_team": fav_team,
            "favored_pct": fav_pct,
            "underdog_team": dog_team,
            "underdog_pct": dog_pct,
        })

    return out


def fetch_covers_consensus(sport: Optional[str] = None, force_refresh: bool = False) -> List[Dict]:
    """Retrieve consensus data from memory cache or Covers.com.
    
    Safe & non-blocking: never raises an exception.
    """
    key = (sport or "all").lower().strip()
    now = time.time()

    with _LOCK:
        if not force_refresh and key in _CACHE:
            if now - _CACHE_TIME.get(key, 0.0) < CACHE_TTL_SECONDS:
                return list(_CACHE[key])

    # Build target URL
    if key in ("all", "top"):
        url = f"{COVERS_BASE_URL}/all"
    elif key in ("nba", "basketball"):
        url = f"{COVERS_BASE_URL}/nba/overall"
    elif key in ("nhl", "hockey"):
        url = f"{COVERS_BASE_URL}/nhl/overall"
    elif key in ("nfl", "football", "american_football"):
        url = f"{COVERS_BASE_URL}/nfl/overall"
    elif key in ("mlb", "baseball"):
        url = f"{COVERS_BASE_URL}/mlb/overall"
    else:
        url = f"{COVERS_BASE_URL}/all"

    try:
        resp = httpx.get(url, headers=HEADERS, timeout=6.0, follow_redirects=True)
        if resp.status_code == 200:
            parsed = parse_covers_html(resp.text)
            if parsed:
                with _LOCK:
                    _CACHE[key] = parsed
                    _CACHE_TIME[key] = now
                return parsed
    except Exception as ex:
        log.debug("Covers.com fetch error (%s): %s", url, ex)

    # If fetch failed, return old cache if present
    with _LOCK:
        if key in _CACHE:
            return list(_CACHE[key])
        if "all" in _CACHE:
            all_cached = _CACHE["all"]
            if sport:
                return [c for c in all_cached if c.get("sport") == sport or c.get("league", "").lower() == sport.lower()]
            return list(all_cached)

    return []
