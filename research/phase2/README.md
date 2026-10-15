# Phase 2: task set

16 verified sqlglot tasks in `eval/tasks_v2/` (fixes from 25 Sep to 14 Oct 2026, after the models' training cutoff).

1. Candidates: fixes touching ≥3 source files or ≥20 lines across files; near-duplicates and the dev task family dropped (18).
2. `verify.py`: hidden tests fail at the base commit and pass at the fix commit (16 of 18; two excluded because a hidden
   test file needs pytz, which the offline environment lacks).
3. Prompts: symptom-only bug reports written from the hidden tests (`prompt_spec.py`); every example's "currently" and
   "expected" output is computed by running it at the base and fix commits (`eval_examples.py`, `examples.json`).
4. Regression tests: every test in the affected test files that passes at both commits, excluding hidden tests
   (`pools.json`, 11–292 per task; SWE-bench pass-to-pass semantics).
5. A8 check (`a8.py`, `a8_full.py`): 96 single-line bugs planted in existing code of the files each fix touched.
   A 11–20-test sample caught 33% of the bugs the full test files catch; the full sets catch 90% (36 of 40).
6. Screening (`screening_results.json`): baseline only, 2 reps per task, Sonnet 5.5 and Haiku 5.5, offline Claude Code.
