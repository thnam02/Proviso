# Regression screen (before the pilot)

Question: do agents ever break existing tests on these tasks? If not, Proviso's regression check has no natural target.

- 10 more verified tasks whose fixes change shared core code (`prompt_spec2.py`, `examples2.json`); bea35b336c excluded
  (pytz), e1e0d2e52f dropped (same feature as 862fd55467).
- Regression sets widened to every existing test in the repository that passes at the base and fix commits
  (`fullpool.py`, `fullpools.json`: about 1,070-1,130 per task); tests the fix commit adds count as hidden checks.
- All 84 screening runs re-graded (`screening_results.json`): Sonnet 32, Haiku 32 on the first 16 tasks, Haiku 20 on
  the 10 core-code tasks.

Result: 0 of 84 runs broke an existing test. Every run ran tests itself (52 of 64 first-batch runs and 19 of 20
core-code runs ran the full suite), spending about 27-32% of their tokens in test-running requests.
