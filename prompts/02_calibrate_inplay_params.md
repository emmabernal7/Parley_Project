# Prompt 2 — Calibrate the in-play priors on real data

Read `AGENTS.md`, `SPEC.md`, and `docs/model_guide.tex` section 6 first.

## Why

`InPlayParams` (`sportsquant/inplay/soccer.py`) currently uses literature-typical defaults for
`beta_score` (score-effect strength), `red_own`/`red_opp` (red-card multipliers), and
`sportsquant/live/providers/weather.py`'s `goal_rate_multiplier` uses an admittedly-uncalibrated
prior. `docs/model_guide.tex` says outright these are priors, not fitted — this prompt fits them.

## Task

1. Run `scripts/ingest.py --all` (or at least the Big 5) to get several seasons of real match data
   with minute-level detail if you can find a free source with goal timings (football-data.co.uk
   does not carry goal minutes — you likely need a secondary source, e.g. a free minute-level
   events dataset, or an ESPN/other play-by-play endpoint you can legally poll and store over
   time going forward). If no minute-level source is available, a coarser calibration is still
   valuable: fit `beta_score` by comparing model-implied vs. empirical additional-goal rates for
   teams currently leading vs. trailing by 1/2 goals, aggregated from full-time and half-time
   scores you already have (you know the score at half-time and full-time, i.e. two snapshots per
   match — that's enough to estimate the score-effect direction and rough magnitude even without
   full minute data).
2. Fit `beta_score`, `red_own`, `red_opp` by maximum likelihood or method-of-moments against
   whatever real signal you assembled, following the existing pattern: write the fit as a method
   returning fitted values plus a way to sanity-check them (e.g. reproduce the observed
   trailing-team second-half scoring uplift).
3. For weather: join match dates/venues with `weather.forecast_at` (you'll need venue lat/lon —
   `venue.py`'s geocoding helper already exists) and regress total goals against wind/precipitation
   to get a real multiplier, replacing the hard-coded `0.95`/`0.97`/`0.93` guesses.
4. Store the fitted values in `config/settings.yaml` (add fields; wire them through
   `InPlayParams`'s construction in `engines/soccer.py::SoccerPricer.__init__` instead of relying
   purely on the dataclass defaults) so they're inspectable and editable without a code change.

## Must

- Add a test that checks the fitted `beta_score` has the correct SIGN (trailing team scores more,
  i.e. `beta_score > 0`) at minimum, even if the exact magnitude is data-dependent and can't be
  hard-asserted.
- Update `docs/model_guide.tex` section 6 to say these are now fitted, with the fitted values and
  how they were obtained — do not leave the document claiming something is a placeholder once it
  isn't; recompile the PDF (`pdflatex model_guide.tex`, run twice) and check it still compiles
  clean.
- Keep `test_beta_zero_matches_independent_poisson` and the other exactness tests in
  `tests/test_inplay_soccer.py` passing unchanged — calibrating the VALUE of beta must not change
  the mathematical correctness of the engine at beta=0 or at kickoff.

## Must not

- Do not fit on the same seasons you'll use to backtest the overall betting strategy later —
  keep a held-out period, the same discipline `DixonColes.fit`'s `ref_date` already enforces
  elsewhere.
