"""Ingest historical results + odds from football-data.co.uk (free, no key, updated ~daily in-season).

Column layout (confirmed against football-data.co.uk's own documentation):
    Div, Date, Time, HomeTeam, AwayTeam, FTHG, FTAG, FTR, HTHG, HTAG, HTR, Referee,
    HS, AS, HST, AST, HF, AF, HC, AC, HY, AY, HR, AR,
    then per-bookmaker odds:  <Book>H, <Book>D, <Book>A  (1X2)  and, for some books, closing prices <Book>CH/CD/CA,
    and totals  <Book>>2.5 / <Book><2.5  (e.g. B365>2.5, B365<2.5, P>2.5, P<2.5).
Not every league/season has every column (Referee and HC/HY/etc. are usually England/Scotland-only, and the
set of bookmakers differs by season), so every read is defensive: a missing column is simply skipped.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import requests

from ..data.store import Store
from ..names import canon

log = logging.getLogger(__name__)

BASE = "https://www.football-data.co.uk/mmz4281"

# division code -> (our league key, display name, tier)
DIVISIONS: Dict[str, tuple] = {
    "E0": ("ENG1", "Premier League", 1), "E1": ("ENG2", "Championship", 2),
    "E2": ("ENG3", "League One", 3), "E3": ("ENG4", "League Two", 4),
    "EC": ("ENG5", "National League", 5),
    "SC0": ("SCO1", "Scottish Premiership", 1), "SC1": ("SCO2", "Scottish Championship", 2),
    "SC2": ("SCO3", "Scottish League One", 3), "SC3": ("SCO4", "Scottish League Two", 4),
    "D1": ("GER1", "Bundesliga", 1), "D2": ("GER2", "2. Bundesliga", 2),
    "SP1": ("ESP1", "La Liga", 1), "SP2": ("ESP2", "La Liga 2", 2),
    "I1": ("ITA1", "Serie A", 1), "I2": ("ITA2", "Serie B", 2),
    "F1": ("FRA1", "Ligue 1", 1), "F2": ("FRA2", "Ligue 2", 2),
    "N1": ("NED1", "Eredivisie", 1), "B1": ("BEL1", "Jupiler Pro League", 1),
    "P1": ("POR1", "Primeira Liga", 1), "T1": ("TUR1", "Super Lig", 1),
    "G1": ("GRE1", "Super League Greece", 1),
}

# preference order for "the" 1X2 price used by the model / de-vig (sharp first)
BOOK_PRIORITY = ["PS", "P", "B365", "BW", "IW", "VC", "WH", "Max", "Avg"]
TOTAL_PRIORITY = ["B365", "P", "Max", "Avg"]


@dataclass
class IngestResult:
    division: str
    league: str
    season: str
    matches: int
    odds_rows: int
    has_referee: bool
    has_cards: bool
    has_corners: bool


class FootballDataIngester:
    def __init__(self, store: Store, timeout: int = 20):
        self.store = store
        self.timeout = timeout

    # -------------------------------------------------------------- fetch
    @staticmethod
    def season_code(season: str) -> str:
        """'2024-2025' | '2024/25' | '24-25' -> '2425'."""
        s = season.replace("/", "-").strip()
        parts = s.split("-")
        if len(parts) == 2 and len(parts[0]) == 4:
            return parts[0][2:] + parts[1][-2:]
        if len(parts) == 2 and len(parts[0]) == 2:
            return parts[0] + parts[1]
        if len(s) == 4:
            return s
        raise ValueError(f"unrecognised season format: {season!r}")

    def fetch_csv(self, division: str, season: str) -> str:
        url = f"{BASE}/{self.season_code(season)}/{division}.csv"
        r = requests.get(url, timeout=self.timeout, headers={"User-Agent": "sportsquant/1.0"})
        r.raise_for_status()
        return r.content.decode("latin-1")

    # -------------------------------------------------------------- parse
    def parse(self, csv_text: str, division: str, season: str) -> pd.DataFrame:
        raw = pd.read_csv(io.StringIO(csv_text), na_values=["", "NA"], low_memory=False)
        raw = raw.dropna(how="all")
        raw.columns = [c.strip() for c in raw.columns]
        if "HomeTeam" not in raw.columns and "Home" in raw.columns:
            raw = raw.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam"})
        need = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]
        missing = [c for c in need if c not in raw.columns]
        if missing:
            raise ValueError(f"{division} {season}: missing required columns {missing}")
        raw = raw.dropna(subset=need).copy()

        def parse_date(s: str) -> Optional[datetime]:
            for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(str(s).strip(), fmt)
                except ValueError:
                    continue
            return None

        raw["date"] = raw["Date"].map(parse_date)
        raw = raw.dropna(subset=["date"])
        raw["time"] = raw["Time"].astype(str) if "Time" in raw.columns else "15:00"
        key, league_name, tier = DIVISIONS.get(division, (division, division, 1))

        out = pd.DataFrame({
            "match_id": [f"{division}_{season}_{i}" for i in raw.index],
            "league": key, "league_name": league_name, "tier": tier, "division": division, "season": season,
            "date": raw["date"], "home": raw["HomeTeam"].map(canon_display), "away": raw["AwayTeam"].map(canon_display),
            "home_raw": raw["HomeTeam"], "away_raw": raw["AwayTeam"],
            "fthg": raw["FTHG"].astype(int), "ftag": raw["FTAG"].astype(int),
            "hthg": raw.get("HTHG"), "htag": raw.get("HTAG"),
            "referee": raw.get("Referee"), "hs": raw.get("HS"), "as_": raw.get("AS"),
            "hst": raw.get("HST"), "ast": raw.get("AST"), "hc": raw.get("HC"), "ac": raw.get("AC"),
            "hy": raw.get("HY"), "ay": raw.get("AY"), "hr": raw.get("HR"), "ar": raw.get("AR"),
        })
        odds = self._extract_odds(raw, out["match_id"].to_numpy())
        return out, odds

    @staticmethod
    def _extract_odds(raw: pd.DataFrame, match_ids) -> pd.DataFrame:
        rows: List[dict] = []
        cols = set(raw.columns)
        for book in BOOK_PRIORITY + ["BW", "IW", "VC", "WH", "LB", "SB", "SJ", "GB"]:
            h, d, a = f"{book}H", f"{book}D", f"{book}A"
            if {h, d, a} <= cols:
                for mid, vh, vd, va in zip(match_ids, raw[h], raw[d], raw[a]):
                    if pd.notna(vh) and pd.notna(vd) and pd.notna(va):
                        rows.append({"match_id": mid, "book": book, "market": "1X2", "home": vh, "draw": vd, "away": va})
            ch, cd, ca = f"{book}CH", f"{book}CD", f"{book}CA"
            if {ch, cd, ca} <= cols:
                for mid, vh, vd, va in zip(match_ids, raw[ch], raw[cd], raw[ca]):
                    if pd.notna(vh) and pd.notna(vd) and pd.notna(va):
                        rows.append({"match_id": mid, "book": book, "market": "1X2_close", "home": vh, "draw": vd, "away": va})
        for book in TOTAL_PRIORITY:
            ov, un = f"{book}>2.5", f"{book}<2.5"
            if {ov, un} <= cols:
                for mid, vo, vu in zip(match_ids, raw[ov], raw[un]):
                    if pd.notna(vo) and pd.notna(vu):
                        rows.append({"match_id": mid, "book": book, "market": "OU2.5", "home": vo, "draw": None, "away": vu})
        return pd.DataFrame(rows)

    # -------------------------------------------------------------- orchestrate
    def ingest(self, division: str, seasons: List[str]) -> List[IngestResult]:
        results = []
        all_m, all_o = [], []
        for season in seasons:
            try:
                text = self.fetch_csv(division, season)
            except requests.RequestException as e:
                log.warning("could not fetch %s %s: %s", division, season, e)
                continue
            try:
                m, o = self.parse(text, division, season)
            except ValueError as e:
                log.warning("could not parse %s %s: %s", division, season, e)
                continue
            all_m.append(m)
            all_o.append(o)
            results.append(IngestResult(division, m["league"].iloc[0], season, len(m), len(o),
                                        m["referee"].notna().any() if "referee" in m else False,
                                        m["hy"].notna().any() if "hy" in m else False,
                                        m["hc"].notna().any() if "hc" in m else False))
        if all_m:
            matches = pd.concat(all_m, ignore_index=True)
            odds = pd.concat(all_o, ignore_index=True) if any(len(o) for o in all_o) else pd.DataFrame()
            self._save(matches, odds)
        return results

    def _save(self, matches: pd.DataFrame, odds: pd.DataFrame) -> None:
        existing = self.store.load_matches()
        if len(existing):
            existing = existing[~existing["match_id"].isin(matches["match_id"])]
            matches = pd.concat([existing, matches], ignore_index=True)
        self.store.save_matches(matches)
        if len(odds):
            with self.store.conn() as c:
                odds.to_sql("odds_history", c, if_exists="append", index=False)


def canon_display(name: str) -> str:
    """Keep the ORIGINAL display spelling but collapse whitespace; matching across sources uses names.canon()."""
    return " ".join(str(name).split())
