# Phase 4 pilot: does Proviso remove self-testing turns?

Setup: 4 tasks (08f2405cfd, 1f8d15bbd6 imperfect for Sonnet; 7d9a6cd599, 818483464b solved) × 2 reps × {baseline,
proviso}, Claude Code with claude-sonnet-5-5, offline, host auth, arm order shuffled per task/rep. 16 runs, $3.99
total. Eval dirs: `/home/claude/eval-pilot-a`, `/home/claude/eval-pilot-b`. Per-run data: `pilot_results.json`
(`analyse.py`); token breakdown by request type: `breakdown_*.json` (`breakdown.py`).

Note: a commit to the repo (this folder's analyse.py, no dc-engine change) tripped the version lock after the first
run of each worker; both workers were resumed with `--resume`. dc-engine source is identical across all 16 runs.

## Result

| mean per run | baseline | proviso |
|---|---|---|
| cost | $0.249 | $0.249 |
| all-in tokens | 435k | 472k (+9%) |
| model requests (main agent) | 11.4 | 12.3 |
| test commands run by the agent | 2.9 | 3.0 |
| full-suite runs by the agent | 1.1 | 1.3 |
| hidden-test score | 0.948 | 0.956 |
| existing tests broken | 0 | 0 |
| wall time | 113 s | 166 s |

Paired per-task relative cost difference: +0.4% (bootstrap 95% CI −5.2% to +5.0%).

Proviso blocks: 3 of 8 runs, all soft ("changed after you last looked"), and in all 3 the agent replied that the
change was intended (it was the fix taking effect). Soft-item precision in the pilot: 0/3. No hard items, no hook
errors. Mean verify time 62 s.

## Why: assumption A5 fails, and the removable share is smaller than measured before

1. Agents kept testing. The instruction ("You do not need to re-run the whole test suite yourself") did not change
   behaviour: agents still run targeted tests after edits and the full suite before answering, so they can tell the
   user "the full suite passes apart from 4 pre-existing pytz errors" (several `git stash` to confirm the errors
   pre-exist).
2. Most test runs are bundled into the edit command (`python - <<EOF ... write file ... EOF; python -m pytest ...`),
   so they cost no extra model request. Baseline token breakdown over 40 Sonnet runs:

   | request type | token share | requests per run |
   |---|---|---|
   | explore (read/grep/list) | 40% | 5.2 |
   | edit (incl. edit + run tests) | 33% | 3.4 |
   | test-only (removable by Proviso) | 11% | 1.2 |
   | final answer | 11% | 1.0 |
   | probe (python snippet) | 4% | 0.5 |

   The earlier "about 30% of tokens in test-running requests" counted bundled edit+test requests. The ceiling for
   removing self-testing turns is about 11% of tokens, before Proviso's own overhead (pushed context, block turns).
3. Pushed context did not reduce exploration: 6.0 explore requests per run with Proviso vs 5.6 without.
