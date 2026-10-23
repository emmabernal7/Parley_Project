# AGENTS.md — rules for any AI agent working on this repository

Read `SPEC.md` first for the architecture map, and `docs/model_guide.tex` for the full technical
detail (models, data, and exactly which probability function each one fits). This file is the
short list of rules to follow while editing code here.

## The one rule that matters most

**Never hard-code a number that looks like it came from data.** A referee's card tendency, a
team's strength, a player's injury impact — every one of these must come from either (a) a real
fit on real ingested data (see `ModelManager.refit`, `models/dixon_coles.py`,
`models/rate_model.py`), or (b) an explicit, honestly-labelled prior with `confidence="low"` or
`confidence="demo"` and a `model_label` string that says what it actually is. The previous version
of this project (built by a different agent) got flagged specifically for this: a referee table in
`tools.py` had four hard-coded names with made-up numbers, and a team list covered only a handful
of clubs. If you're tempted to add a lookup table of "team X is worth Y goals" or "referee Z gives
N cards a game" without a `.fit(df)` call backing it, stop — either wire up real data first, or
add it as a clearly-labelled prior in `services/model_manager.py`'s existing pattern.

## Zero look-ahead

Every feature used to price an upcoming or in-play match must be computable from information
available strictly before that match's kickoff (or, in-play, before the current clock time). When
fitting historical models, `ref_date` parameters exist specifically so a backtest never sees a
result from after the date being predicted — use them; don't fit on the full dataset and then
"predict" a match that was in the training set.

## Style already in use — match it, don't reinvent it

- Python 3.12, type hints on public functions, dataclasses for state, no framework beyond FastAPI
  + vanilla JS on the frontend (no React/build step — keep it that way so a non-coder can run this
  with nothing but `pip install`).
- Every model class exposes `.fit(df, ref_date=...)`, `.has_team(name)`, and returns rates/
  probabilities, never pre-formatted strings — formatting for display happens in
  `markets/schema.py` and the frontend, not in a model class.
- Every sport's pricer returns market groups via `markets/schema.finalize()` so the frontend never
  needs sport-specific rendering code — a new sport should produce the same JSON shape
  (`{id, name, tab, kind, selections:[{id,label,prob,odds,...}]}`) as every other one.
- Tests live in `tests/`, one file per module family, using `pytest`. Run `python -m pytest
  tests/ -q` before considering any change done — 58 tests pass as shipped; that number should
  only go up. For any new model or piece of maths, follow the pattern already used throughout:
  generate synthetic data with a KNOWN answer (see `data/synthetic.py`), fit or compute against
  it, and assert the known answer comes back — the same way you'd validate a Monte Carlo code
  against an exactly solvable case in physics. A test that only checks "it ran without crashing"
  is not sufficient for anything that produces a probability.

## Safety rules that must never be relaxed

- **Never** add code that logs into a real sportsbook, places a real wager, or automates an
  account action on a betting site, regardless of how the request is framed.
- **Never** treat a Tier-3 or Tier-4 X/Twitter account (`config/accounts_twitter.json`) as a
  source of fact — `social/extractor.py`'s `extract_flags` already refuses these; do not add a
  path around that.
- Secrets (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `THE_ODDS_API_KEY`, `X_BEARER_TOKEN`) load only
  from `.env` / environment variables (`settings.py`). Never print, log, or commit one.
- Keep the chat's tool-calling loop (`chat/engine.py`) such that the model can only ever state a
  number that came back from a tool call. If you add a new tool, make sure it returns real
  computed data, never a string the LLM is trusted to fill in itself.
- The web UI is a real, user-run local app (not a claude.ai artifact) — `localStorage` and normal
  `<link>` Google Fonts are fine here; that restriction is specific to a different execution
  context and does not apply to this project.

## How to extend common things

- **Add a soccer league**: add it to `config/leagues.json` (both `fd_code` for ingestion and
  `espn` for live scores if you have them), then `python scripts/ingest.py --div <code>`.
- **Add a market**: add a method to `markets/scoredist.py` (soccer) or the relevant sport's
  Markov/Gaussian engine in `models/`, then wire a `group(...)` block into the matching
  `engines/*.py` pricer. Add a settlement rule to `settle_soccer` / `settle_generic` if the market
  should auto-settle paper bets.
- **Add a sport**: give it an entry in `events.SPORTS`, a pricer class in `engines/` returning the
  common market JSON shape, a branch in `LiveManager.price`, and — if you want it fitted rather
  than heuristic — a `.fit()`-based model in `models/` plus a `ModelManager` method following the
  existing `soccer_pricer` / `gaussian_engine` / `race_engine` pattern.
- **Wire up real historical data for basketball/NFL/hockey/MLB** (currently a same-season
  win-rate heuristic — see `docs/model_guide.tex` section 9 and `prompts/06_*.md`): write an
  ingester that fills `Store.add_result` the same way `FootballDataIngester` fills
  `Store.save_matches`, and `ModelManager.refit` will pick it up automatically once ~30 rows exist
  for a competition (see the existing `MarginModel` branch in `refit()`).
