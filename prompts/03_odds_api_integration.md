# Prompt 3 — Automatic bookmaker odds via The Odds API

Read `AGENTS.md` and `SPEC.md` first.

## Why

Today, checking for +EV requires typing a price in by hand (right-click a selection ->
`/api/event/{id}/odds`). `settings.odds_api_key` already exists and is read from `.env`
(`THE_ODDS_API_KEY`) but nothing calls it yet. This prompt closes that loop.

## Task

1. Write `sportsquant/live/providers/odds_api.py` following the exact shape of
   `providers/espn.py`: a `fetch(sport, league, ...)` function that calls
   `https://api.the-odds-api.com/v4/sports/{sport_key}/odds` (check their current docs for exact
   sport keys and query params — `apiKey`, `regions`, `markets`, `oddsFormat=decimal`), fails soft
   (returns `[]`, logs a warning) on any error including a missing/invalid key, and returns a list
   of `{event match key, bookmaker, market, selection, odds}` rows — do NOT try to force this into
   the `Event` dataclass; odds need their own shape since one event has many bookmakers x many
   markets.
2. In `LiveManager`, add a method `refresh_market_odds()` that matches each odds-API event to an
   existing `Event` by team names (`names.best_match`, already handles fuzzy matching — reuse it,
   don't write a second matcher) and stores the best (e.g. median, or a named reference book like
   Pinnacle if present) price per market into `Event.market_odds`.
3. In `LiveManager.price`, when `ev.market_odds` has a price for a selection and the user hasn't
   typed in their own price for that same key, surface the fetched price as `sel["book_odds"]`
   (a new field, additive — do not replace `user_odds`, they answer different questions: "what
   the market says" vs. "what I've been quoted"). Update `ToolBox.find_value` to also scan
   `book_odds` when `user_odds` is absent for a selection.
4. Add a `/api/data-status` field showing whether the odds API key is configured and when it was
   last polled successfully, and surface it in the UI's info panel.

## Must

- Respect the free-tier request budget (500 credits/month at the time this was written — verify
  current limits): poll on `settings.poll_schedule_seconds`-style cadence, not every request, and
  make the interval configurable in `config/settings.yaml`.
- Add tests mocking the HTTP call (see `tests/test_ingestion.py`'s ESPN tests for the pattern:
  capture one real response as a fixture first, then mock).
- Keep working with no key set — this is an enhancement, not a requirement; `test_data_status_and_social_status`-style tests should still pass with the key absent.

## Must not

- Do not remove the manual "right-click to enter your own price" flow — some markets (props,
  specials) may never appear on a free odds API tier, and manual entry is the fallback for those.
