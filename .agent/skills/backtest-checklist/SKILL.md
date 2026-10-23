# Skill: backtest checklist

Trigger: fitting or evaluating any model on historical data.

Before you trust a number:
1. Walk-forward only. Use each model's `ref_date` parameter — fit on data strictly before the
   period you're evaluating. Never fit and evaluate on overlapping matches.
2. Generate synthetic data with KNOWN true parameters first (`data/synthetic.py`), confirm the
   fit recovers them, before trusting the fit on real data. This project's whole test suite
   follows this pattern (`tests/test_dixon_coles.py`, `tests/test_inplay_soccer.py`) — match it.
3. Report log loss and Brier score, not just accuracy or a single backtest's profit — a model can
   look profitable on a lucky sample and still be poorly calibrated.
4. Compare against the closing line (de-vigged), not the opening line — see
   `prompts/05_bankroll_ledger_and_backtest.md` for the full CLV backtest task.
5. State the exact seasons/leagues/date ranges used, in the code AND in `docs/model_guide.tex` —
   an unreproducible backtest is not evidence of anything.
