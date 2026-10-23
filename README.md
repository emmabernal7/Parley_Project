# SportsQuant

A statistics-based sports prediction engine with a Stake-style web interface, a bet-slip and
paper-trading ledger, and a chat assistant — for soccer (many leagues), NBA, NFL, NHL, MLB, tennis,
volleyball, MMA and F1.

**This is a research / paper-trading tool. It never places a real bet or logs into a sportsbook.**
Read `docs/model_guide.tex` (or the compiled PDF) for exactly which numbers are fitted on real
data and which are placeholders — the app shows this on every match as a confidence badge.

## 1. Install Python

You need Python 3.11 or 3.12. Check with:

```
python3 --version
```

If that fails or shows an older version, install Python from https://python.org/downloads (tick
"Add to PATH" on Windows) or via Antigravity's own environment if you're running this from there.

## 2. Install the project's dependencies

Open a terminal in this folder and run:

```
pip install -r requirements.txt
```

(If `pip` isn't found, try `pip3` or `python3 -m pip`.)

## 3. Get real match history (recommended, takes under a minute)

```
python scripts/ingest.py
```

This downloads a few seasons of the top 5 leagues (England, Spain, Italy, Germany, France) from
the free site football-data.co.uk. Run `python scripts/ingest.py --all` to pull every league
listed in `config/leagues.json`, or `python scripts/ingest.py --div E0 E1 SP1` for specific ones —
run `python scripts/ingest.py --help` for all the options.

**Skip this step and the app still works** — soccer matches just show an amber "low-confidence
prior" badge instead of a green "fitted model" one, until you run it.

## 4. (Optional) API keys

Copy `.env.example` to `.env` and fill in anything you have. Every line is optional:

- **THE_ODDS_API_KEY** — compares your fair odds against real bookmaker prices (free tier at
  https://the-odds-api.com).
- **ANTHROPIC_API_KEY** or **GEMINI_API_KEY** — turns the chat from the built-in offline
  keyword-router into a full conversational assistant using your own key. Leave both blank and the
  chat still works, just less flexibly.
- **X_BEARER_TOKEN** — turns on the (optional, off by default) Twitter/X news layer. Reading X's
  API is not free — see `docs/model_guide.tex` section 8 before turning this on.

## 5. Start it

```
python run.py
```

This opens http://127.0.0.1:8000 in your browser automatically. Leave the terminal window open —
closing it stops the server.

## What you'll see

- A sport rail on the left, a match list, and (once you pick a match) every market — 1x2, totals,
  Asian handicaps, half-time/full-time, cards, corners, same-game multis, minute markets — with
  both a probability percentage and a fair decimal price. Toggle between the two in the top bar.
- A few clearly-labelled **DEMO** matches always running (e.g. Barcelona vs Galatasaray on a
  compressed ~8-minute clock) so you can watch the price move after a goal without waiting for a
  real kickoff — see `docs/model_guide.tex` section 10 for exactly how that works and why it's
  a legitimate demonstration rather than a scripted animation.
- Click a price to add it to your bet slip (bottom right); the chat (💬, bottom right) can price
  same-match parlays correctly (accounting for correlation between legs), scan for value against
  odds you type in, size a Kelly stake, or just answer "what are the odds on Barcelona".
- "My paper bets" (the ☰ icon, top right) shows every paper bet you've placed and its running
  profit/loss once it settles automatically.

## Project layout

```
sportsquant/        the actual application (see docs/model_guide.tex for how it all fits together)
scripts/ingest.py   one-off / periodic real-data ingestion (run this, not part of the live server)
config/             leagues, settings, and the tiered X/Twitter account list
docs/model_guide.tex   the full technical writeup — models, data, and the exact probability
                       functions being fit, plus what was tested and how
prompts/            ready-to-paste prompts for continuing this project with Antigravity
AGENTS.md           rules for any AI coding agent (Antigravity, Claude Code, ...) working on this repo
SPEC.md             architecture reference for an agent picking this project back up
tests/              pytest suite (`python -m pytest tests/ -q`) — 58 tests, all passing as shipped
```

## Troubleshooting

- **"No matches right now"** — the demo matches should always be there; if even those are missing,
  check the terminal for errors and confirm `providers` in `config/settings.yaml` includes `sim`.
- **Soccer badges stay amber** — run `python scripts/ingest.py` (step 3); check your internet
  connection if it reports 0 matches ingested.
- **Port already in use** — set `port:` to something else (e.g. 8001) in `config/settings.yaml`.
- **Chat feels repetitive / limited** — that's the offline router; add an API key (step 4) for a
  full conversational assistant.
