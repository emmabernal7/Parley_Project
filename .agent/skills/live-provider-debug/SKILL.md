# Skill: debugging a live data provider

Trigger: a live provider (`sportsquant/live/providers/*.py`) returns empty or wrong data.

1. These are unofficial/undocumented APIs (ESPN especially) — they change without notice. Fetch
   one real response by hand first (curl, or your browser's network tab) and compare it against
   the fixture in `tests/fixtures/` before assuming the parsing code is wrong.
2. Save the new real response as an updated fixture and update the matching test in
   `tests/test_ingestion.py` BEFORE fixing the parser — this is exactly how a real bug was caught
   during this project's own build (odds were nested under the wrong JSON key; the fixture test
   caught it immediately).
3. Every provider function must fail soft: return `[]` (or `None` for a single lookup), log a
   warning, never raise out of `LiveManager`'s polling loop. Check this with a test that mocks
   `requests.get` to raise a connection error and asserts an empty result, not an exception.
4. Never widen a provider's network access beyond read-only GET requests to the documented (even
   if unofficial) endpoint — no login flows, no write actions, ever.
