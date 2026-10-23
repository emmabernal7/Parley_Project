# Prompt 1 — Real historical ingestion for basketball, NFL, hockey, MLB

Read `AGENTS.md` and `SPEC.md` first. Plan before you build.

## Why

Soccer already fits a real Dixon-Coles model on real football-data.co.uk history
(`sportsquant/ingest/footballdata.py`). The other four sports currently price matches from a
same-season ESPN win/loss record heuristic (`ModelManager._record_heuristic`, confidence="low").
This prompt replaces that heuristic with a real fit, the same way soccer already works.

## Task

For **one sport at a time** (start with NBA), write `sportsquant/ingest/<sport>.py` that:

1. Pulls multiple seasons of historical game results (final score, date, home/away team, and
   ideally pace/possessions if the source has them) from a free source. Suggested starting points
   (verify current availability/ToS yourself — do not scrape a source that forbids it):
   - NBA: `nba_api` (PyPI) or basketball-reference's own season schedule CSVs.
   - NFL: `nflreadpy` (PyPI) — play-by-play and schedules; aggregate to game-level scores.
   - NHL: the NHL's own public stats API (`api-web.nhle.com`).
   - MLB: `MLB-StatsAPI` (PyPI wrapper around `statsapi.mlb.com`) or `pybaseball`.
2. Writes rows into the existing `results` table via `Store.add_result(rid, sport, competition,
   date, home, away, home_score, away_score, source, extra)` — reuse this table, don't create a
   new one.
3. Follows the exact pattern of `scripts/ingest.py`: a standalone CLI script
   (`scripts/ingest_<sport>.py`), clear console output, and a graceful "0 rows, check your
   connection" message on failure rather than a crash.

`ModelManager.refit()` already has a branch that fits a `MarginModel` on the `results` table the
moment ~30 rows exist for a `(sport, competition)` pair (see the `results.groupby(["sport",
"competition"])` loop) — you should not need to touch `ModelManager` for NBA/NFL. You likely DO
need a hockey/MLB-specific fit (Poisson race, not margin) — add a `race_engine` fitted branch
mirroring `soccer_pricer`'s "try fitted, fall back to heuristic, label honestly" structure; do not
remove the heuristic fallback, only make it the fallback rather than the only option.

## Must

- Write the ingester, run it once for real (this needs real internet access — an Antigravity
  agent running locally has this; a sandboxed one may not), and report how many rows landed.
- Add a `tests/test_ingest_<sport>.py` following the pattern in `tests/test_ingestion.py`: capture
  one real API response as a fixture, test the parser against it, mock the network for the
  end-to-end test.
- Run `python -m pytest tests/ -q` and confirm the count only goes up from 58.
- Update the confidence badge logic so a fitted competition shows "ok", not "low" — verify this in
  the running app, not just by reading the code.

## Must not

- Do not remove or weaken the existing heuristic fallback — competitions you haven't ingested yet
  must keep working, just with the honest amber badge.
- Do not touch `sportsquant/engines/soccer.py` or anything under `models/dixon_coles.py` — out of
  scope for this prompt.
