#!/usr/bin/env python3
"""Pull real match history + odds from football-data.co.uk into the local database.

Run this once before starting the app (and again occasionally to refresh):

    python scripts/ingest.py                        # Big-5 leagues, last 3 seasons
    python scripts/ingest.py --all                   # every league in config/leagues.json that has one
    python scripts/ingest.py --div E0 E1 SP1 --seasons 2022-2023 2023-2024 2024-2025

Needs a normal internet connection (this is the one step that can't run inside a sandboxed
container - see README.md).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sportsquant.data.store import Store
from sportsquant.ingest.footballdata import DIVISIONS
from sportsquant.ingest.footballdata import FootballDataIngester
from sportsquant.settings import CONFIG_DIR, get_settings

BIG5 = ["E0", "SP1", "D1", "I1", "F1"]


def default_seasons(n: int) -> list[str]:
    import datetime
    y = datetime.date.today().year
    return [f"{yy}-{yy+1}" for yy in range(y - n, y + 1)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--div", nargs="*", default=None, help="football-data.co.uk division codes, e.g. E0 SP1 D1")
    ap.add_argument("--all", action="store_true", help="ingest every division listed in config/leagues.json")
    ap.add_argument("--seasons", nargs="*", default=None, help="e.g. 2022-2023 2023-2024 2024-2025")
    ap.add_argument("--years", type=int, default=None, help="shortcut: last N seasons up to the current one")
    args = ap.parse_args()

    if args.all:
        leagues = json.loads((CONFIG_DIR / "leagues.json").read_text(encoding="utf-8"))
        divisions = [l["fd_code"] for l in leagues.get("soccer", []) if l.get("fd_code")]
    else:
        divisions = args.div or BIG5

    s = get_settings()
    seasons = args.seasons or default_seasons(args.years or s.lookback_seasons)

    store = Store(s.db_path)
    ing = FootballDataIngester(store)
    print(f"Ingesting {len(divisions)} division(s) x {len(seasons)} season(s) into {s.db_path}")
    print(f"Divisions: {', '.join(divisions)}")
    print(f"Seasons:   {', '.join(seasons)}\n")

    total = 0
    for div in divisions:
        name = DIVISIONS.get(div, (div, div, 0))[1]
        results = ing.ingest(div, seasons)
        got = sum(r.matches for r in results)
        total += got
        flags = []
        if results and any(r.has_referee for r in results):
            flags.append("referees")
        if results and any(r.has_cards for r in results):
            flags.append("cards")
        if results and any(r.has_corners for r in results):
            flags.append("corners")
        extra = f" (+{', '.join(flags)})" if flags else ""
        print(f"  {div:5s} {name:28s} {got:5d} matches{extra}")
        if not results:
            print(f"        -> nothing came back. Check your internet connection, or that {div} "
                  f"has data for the seasons requested (football-data.co.uk is usually a season or two behind for lower divisions).")

    print(f"\nDone - {total} matches stored. Start the app with: python run.py")
    if total == 0:
        print("\nNo data was ingested. This script needs real internet access to www.football-data.co.uk; "
              "it will not work from inside a locked-down container. The app still runs without this "
              "step, but soccer prices fall back to a league-average prior until you run it successfully.")


if __name__ == "__main__":
    main()
