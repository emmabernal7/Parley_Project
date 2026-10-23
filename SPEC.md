# SPEC.md — architecture reference

For *why* things are built this way and the exact maths, see `docs/model_guide.tex`. This file is
the quick map: modules, data schemas, and the JSON contracts that hold the system together.

## Module map

```
sportsquant/
  odds.py              decimal/probability/American/fractional conversions, de-vig, edge, Kelly, CLV
  mathutil.py           Poisson/negative-binomial pmfs, normal cdf
  events.py             Event dataclass — the one object every provider/engine/API/UI agrees on
  settings.py            defaults -> config/settings.yaml -> .env / environment (in that priority)
  names.py               team-name canonicalisation + fuzzy matching across data sources

  models/
    dixon_coles.py        soccer goals model (fit + grid + rates)
    rate_model.py          cards/corners count model (team + referee effects)
    margin_model.py         ridge margin/total model (basketball, NFL)
    racket.py               exact tennis/volleyball point-by-point Markov chains
    elo.py                    Elo ratings + Elo<->goals bridge (cross-league ties)

  inplay/
    soccer.py              minute-by-minute in-play DP (score effects, red cards, terminal tilt)
    generic.py              Gaussian margin-in-play, Poisson-race-in-play, tie-break resolution

  markets/
    scoredist.py           ScoreDist: every soccer market read off one joint scoreline table
    schema.py                common {group, selection} JSON shape used by every sport

  engines/
    soccer.py               SoccerPricer: builds every soccer market group from a ScoreDist
    others.py                 Gaussian/PoissonRace/Tennis/Volleyball/MMA/F1 pricers, same JSON shape

  data/
    store.py                SQLite persistence (matches, results, user odds, paper slips)
    synthetic.py              synthetic leagues with KNOWN ground truth, for tests + the demo card

  ingest/
    footballdata.py         real football-data.co.uk CSV ingestion (soccer history + odds)

  live/
    manager.py               LiveManager: event cache, background polling, on-demand pricing, settlement
    providers/
      espn.py                 real ESPN scoreboard JSON (all sports), fails soft
      weather.py                Open-Meteo, fails soft
      sim_demo.py               the always-on demo universe (draws from the real in-play engine)

  services/
    model_manager.py        fits/caches models per league, resolves team names, honesty labelling

  social/
    extractor.py             tiered X/Twitter reader — inactive without your own bearer token

  chat/
    tools.py                  ToolBox: the real functions (find_event, price_parlay, find_value, ...)
    engine.py                   OfflineChat (zero-config) + AnthropicChat/GeminiChat tool-calling loops

  web/
    app.py                    FastAPI app and every /api/* endpoint
    static/                    index.html, css/app.css, js/app.js (vanilla JS, no build step)
```

## Data model (SQLite, `data/store.py`)

- `matches` — one row per soccer match: `match_id, league, league_name, tier, division, season,
  date, home, away, home_raw, away_raw, fthg, ftag, hthg, htag, referee, hs, as_, hst, ast, hc, ac,
  hy, ay, hr, ar`. Written by `FootballDataIngester`, read by `ModelManager.refit`.
- `odds_history` — long format: `match_id, book, market ('1X2'|'1X2_close'|'OU2.5'), home, draw,
  away`. Not yet consumed by any model — available for a future closing-line-value backtest.
- `results` — generic (sport, competition) results table for non-soccer history, keyed by `rid`.
  `MarginModel` picks this up automatically once ~30 rows exist for a competition.
- `user_odds` — `(event_id, key) -> odds`: prices you typed in, keyed the same way as a market
  selection (`"1x2:home"`).
- `slips` — paper bet slips: `stake, legs (json), status (open|won|lost|void), pnl`.
- `kv` — generic key/value scratch space, currently unused by the shipped app but there for agents
  who need a place to persist a small piece of state without a schema migration.

## The Event contract (`events.py`)

Every provider (ESPN, the demo universe) and every consumer (LiveManager, the pricing engines, the
API) agrees on one `Event` dataclass: `id, sport, competition, home, away, kickoff, status
(scheduled|live|finished|postponed), score, clock (sport-specific live state), live (extra
in-play state e.g. goal sequence / sets / points), venue, referee, weather, market_odds, meta
(free-form: ESPN bet lines, demo lam/mu/rho, records, ...), source (espn|demo)`.

## The market JSON contract (`markets/schema.py`)

Every pricer, whatever the sport, returns a list of groups shaped like:

```json
{
  "id": "1x2", "name": "1x2", "tab": "main", "kind": "3way",
  "selections": [
    {"id": "home", "label": "Barcelona", "prob": 0.74, "odds": 1.35, "line": null}
  ],
  "note": "optional"
}
```

`tab` is one of `main | sgm | goals | asian | half | lines | specials | minute` and drives which
tab a group appears under in the UI (`TAB_ORDER` in `static/js/app.js`). `prob` is always the
model's own probability; `odds = 1/prob` is filled in by `finalize()`. A `user_odds` field is
added at serving time (`LiveManager.price`) when you've typed in a price for that exact
`group_id:selection_id` key.

## Confidence labelling (see also `docs/model_guide.tex` §9)

Every pricer constructor takes `model_label: str` and `confidence: "ok" | "low" | "demo"`, surfaced
in the `info` block of `/api/event/{id}` and rendered as the badge in the UI header. Never return
`confidence="ok"` from a code path that isn't backed by a real `.fit()` on real data.

## Adding a new sport end-to-end (checklist)

1. Add the sport id to `events.SPORTS` / `SPORT_LABELS`.
2. Add a league entry to `config/leagues.json` with its ESPN slug (verify against
   `site.api.espn.com/apis/site/v2/sports/<sport>/<league>/scoreboard` — these are unofficial and
   occasionally change).
3. Write a pricer in `engines/` returning the common market JSON shape (copy the closest existing
   engine in `engines/others.py` as a template).
4. Add a branch in `LiveManager.price` dispatching to it.
5. If you have historical data to fit: add a model in `models/`, a fit call in
   `ModelManager.refit`, and a resolution method (see `soccer_pricer` / `gaussian_engine` for the
   pattern: try a fitted model, fall back to a clearly-labelled heuristic, never silently guess).
6. Add tests following the synthetic-ground-truth pattern in `tests/`.
