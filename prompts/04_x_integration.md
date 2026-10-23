# Prompt 4 — Finish the X/Twitter extraction pipeline (only once you have a bearer token)

Read `AGENTS.md` and `SPEC.md`, and `docs/model_guide.tex` section 8, first. **Do not start this
prompt unless the user has explicitly decided to pay for X API access and put a real token in
`X_BEARER_TOKEN`.** The account tiering and the API client already exist
(`sportsquant/social/extractor.py`, `config/accounts_twitter.json`) and are inactive by design.

## Task

1. Implement `llm_extract(text) -> dict | None` for `SocialExtractor.extract_flags` to call: given
   one post's text, ask an LLM (reuse `chat/engine.py`'s existing Anthropic/Gemini HTTP call
   pattern — do not write a third HTTP client) to return strict JSON:
   `{"team": str, "player": str|null, "status": "confirmed_out"|"doubtful"|"confirmed_in"|
   "lineup_confirmed"|"other"|null, "confidence": "high"|"medium"}` or `null` if the post has no
   actionable team-news content. Reject/ignore anything that doesn't parse as that exact schema —
   do not let a malformed LLM response silently become a fabricated flag.
2. Add a background poll (mirroring `LiveManager._loop`'s cadence pattern, its own configurable
   interval in `config/settings.yaml`, e.g. `social_poll_minutes`, default something conservative
   like 240 given the per-post cost) that calls `SocialExtractor.poll()` for Tier 1-2 accounts
   only, runs `extract_flags`, and stores results keyed by team name (a new small table in
   `Store`, e.g. `social_flags(team, player, status, source, tier, confidence, created_at)` —
   follow the existing `Store` method style, don't reach into raw SQL from outside `store.py`).
3. Feed a `confirmed_out` flag for a player into the pre-match rate as an explicit, small,
   DOCUMENTED multiplier on that team's attack rate (proportional to the fitted club's reliance on
   that player if you can estimate it, otherwise a conservative flat discount) — expose it in the
   match's `info.model` label so it's visible, e.g. "Dixon-Coles fitted on 1900 matches (adjusted:
   Player X confirmed out)". Never apply this silently.
4. Surface the flags feeding a given match in the UI's info panel with the source account and a
   link, so the user can judge the source themselves.

## Must

- Only Tier 1/2 accounts may ever produce a stored flag — `extract_flags` already enforces this;
  do not add a path that lets Tier 3/4 through, even "just for testing".
- Cost-track: log an estimate of API spend (posts read x price-per-read) somewhere visible
  (`/api/social/status` already exists — extend it with a running total) so the user can see what
  this is costing them.
- Add tests with a mocked LLM extraction function and a mocked X API response — never call the
  real paid API from the test suite.

## Must not

- Do not decode, list, or explain what makes any specific account "parody" vs "real" beyond what's
  already in `config/accounts_twitter.json` — that judgement call belongs to the user, not to
  code you write.
- Do not build anything that reads Tier 4 (banter/parody) content into anything other than an
  explicitly-labelled, optional "community sentiment" field that never touches a match's price.
