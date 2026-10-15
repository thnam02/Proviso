# Phase 0: feasibility of trajectory-mined contracts

Retrospective check, no new agent runs. Data: the 6 Claude Code runs (Opus 5.5) on sqlglot task
98bedf649b from `eval_claude/`, all correct.

| Step | Script | Output |
| --- | --- | --- |
| Extract the Python each agent ran, with what it saw | `probes.py` | `probes.json` |
| Replay on original vs final code, classify (block-level rule) | `classify2.py` (uses `replay.py`) | `classify2.json` |
| Existing test suite as regression checks | `suites.py` | `suites.json` |
| 10 planted bugs: scripts vs original, vs last-seen, tests, hidden tests | `mutants.py`, `seed.py`, `seed2.py` | `seed_results.json` |

Results (details in the methodology doc):

- Usable scripts in 6/6 runs; 0/14 flaky; 0.16 s per script replay, 46 s for the full test suite.
- False alarms: whole-script rule 5/6 correct runs; block-level rule 1/6.
- Planted bugs caught: agent scripts vs original code 4/10, vs last-seen working state 9/10,
  existing tests 7/10, hidden upstream tests 9/10; scripts + tests 9/10.

Paths in the scripts point at the cloud workspace where the runs lived (`/home/claude/...`).
