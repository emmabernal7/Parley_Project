# Skill: add a new sport engine

Trigger: asked to add pricing for a sport not yet in `sportsquant/events.SPORTS`.

Steps:
1. Read `SPEC.md`'s "Adding a new sport end-to-end" checklist and `sportsquant/engines/others.py`
   for the closest existing template (Gaussian for margin sports, PoissonRace for count sports,
   the Markov chain pattern for point-by-point sports).
2. Every pricer returns `markets.schema.finalize(groups)` — copy that return convention exactly.
3. Add the honesty split in `services/model_manager.py`: a `.fit()`-backed path when data exists,
   a clearly-labelled fallback when it doesn't. Never skip the fallback's `model_label`/`confidence`.
4. Add tests using `data/synthetic.py`'s pattern (known ground truth, check recovery) before
   wiring it into `LiveManager.price`.
5. Run `python -m pytest tests/ -q` — must stay green.
