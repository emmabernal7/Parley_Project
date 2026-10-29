# SportsQuant v2

> **Plataforma cuantitativa de modelado deportivo y paper trading en tiempo real. Modela probabilidades justas (+EV) y devigging mediante Dixon-Coles, Poisson y Empirical Bayes para fútbol, béisbol, baloncesto y más. Incluye simulación de apuestas, asistente conversacional y sincronización con feeds de ESPN. Sin dinero real, 100% analítico.**

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/pytest-60%2F60%20passed-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 🚀 Inicio Rápido en Windows (1 Clic)

Simplemente haz doble clic en el archivo:
- **`iniciar_sportsquant.bat`** (o **`run.bat`**)

El script detectará automáticamente tu instalación de Python/Miniconda, levantará el servidor local y abrirá la interfaz gráfica en tu navegador en:
👉 **`http://127.0.0.1:8000`**

---

## 🛠️ Instalación Manual

### 1. Requisitos de Python
Requiere Python 3.11+. Verifica tu versión:
```bash
python --version
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Ejecutar la plataforma
```bash
python run.py
```
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
