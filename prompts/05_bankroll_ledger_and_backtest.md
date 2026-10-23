# Prompt 5 — A real bankroll ledger, and a closing-line-value report

Read `AGENTS.md` and `SPEC.md` first.

## Why

Today the "bankroll" shown in the top bar is a fixed reference number (`settings.bankroll`) used
only for Kelly-stake sizing; the frontend fakes a running total by summing `pnl` over
`/api/bets` client-side (see `refreshBankrollDisplay` in `static/js/app.js`). There's also no
report yet on whether this project's own model would have beaten the closing line historically —
the single most important number for deciding whether any of this is worth using with real stakes
later.

## Task

### A. Bankroll ledger
1. Add a `ledger` table to `Store` (`ts, delta, reason, ref_slip_id`) and debit it when a paper bet
   is placed (`-stake`) and credit it when a slip settles (`+stake*multiplier` on a win, `+stake`
   on a void, `0` on a loss — i.e. mirror real settlement, not just net pnl).
2. Add `Store.balance()` returning `settings.bankroll + sum(ledger.delta)`. Expose it at
   `/api/bankroll`. Update the frontend to call this instead of recomputing it client-side from
   `/api/bets`.
3. Add a "reset paper bankroll" action (clears the ledger, does not touch settled-bet history)
   since a paper-trading run is meant to be restartable.

### B. Closing-line-value report
1. `odds_history` (populated by `FootballDataIngester._extract_odds`) already has opening AND
   closing prices for some bookmakers (the `*CH/CD/CA` columns, market `"1X2_close"`) for
   historical matches. Write `scripts/backtest_clv.py`: for each historical match in a held-out
   period (use `DixonColes.fit(df, ref_date=...)` fit only on matches BEFORE that period, exactly
   like the existing walk-forward pattern), compute the model's fair probability, de-vig the
   closing price (`sportsquant.odds.devig`), and compute `clv_pct` (already implemented in
   `odds.py`) as if a bet had been placed on whichever side the model favoured.
2. Report, per league: mean CLV%, % of bets with positive CLV, log-loss and Brier score of the
   model's own probabilities against the actual results (calibration, not just CLV) — this is the
   real evaluation described in `docs/model_guide.tex`; write the numbers there once you have
   them, in a new subsection, with the exact seasons/leagues used and the walk-forward split dates
   stated explicitly.
3. Add a calibration plot (predicted probability bucket vs. actual frequency) — a static PNG via
   matplotlib is fine, saved to `reports/`, referenced from the LaTeX doc.

## Must

- The backtest must be genuinely walk-forward: never fit on a season and evaluate on part of that
  same season. Reuse the `ref_date` mechanism already in `DixonColes.fit` — don't build a second
  one.
- Add tests for `Store.balance()` and the ledger debit/credit logic using the existing
  `tmp_store` fixture pattern in `tests/conftest.py`.
- If the CLV report comes back negative (the model does not beat the closing line), report that
  plainly in the document — the point of this exercise is to find out, not to produce a good
  headline number. Re-read `docs/model_guide.tex` section 16 (Honest limitations) before writing
  the new subsection so the tone matches.

## Must not

- Do not remove or bypass the existing paper-bet flow (`/api/bets`) — the ledger is additive
  bookkeeping on top of it, not a replacement.
- Do not use this backtest's results to change `settings.value_min_edge` or
  `settings.kelly_fraction` defaults without saying so explicitly in the same commit/PR
  description — those are the user's risk settings, not something to silently tune.
