# Agent study: does the blast-radius report help a coding agent?

Three arms, run with Claude Code (Sonnet) on 12 real sqlglot fix tasks, 2 repetitions each (72 runs):

| Arm | What the agent gets |
|---|---|
| `baseline` | nothing extra; it runs whatever tests it chooses |
| `impact-noreport` | Proviso rewrites broad test commands to the affected tests; no report |
| `impact` | the same, plus the blast-radius report (edited functions, import-time values that changed, inheriting classes, affected tests) |

`impact` vs `impact-noreport` isolates the report; `impact-noreport` vs `baseline` isolates test selection.

**Tasks** (`eval/tasks/`): 6 "ripple-prone" fixes, where a change can carry over into dialects that inherit the
changed code, and 6 complex fixes, all from sqlglot's history. Each task has a base commit, the issue as the prompt,
hidden tests (the fix must make them pass), and the existing tests that must keep passing.

**Measures** (per run, from the harness): hidden tests passed, existing tests broken (regressions), wall time, API
cost, model requests, test commands run by the agent.

**Run it**: `bash research/agent/run_study.sh`, in WSL with `ANTHROPIC_API_KEY` exported. Each run gives the agent a
full shell, so use a Linux user without SSH keys, git credentials or other secrets (see the script header). The harness
(`src/dc_eval`) is the one used for the earlier pilots; `build_assets.py` builds the v2 dependency map, base failures
and import-time snapshot per task.

**Caveat**: earlier pilots saw few regressions (0–0.25 per run), so 72 runs can show time, cost and how agents use
the report, but probably not a statistically reliable change in regressions.
