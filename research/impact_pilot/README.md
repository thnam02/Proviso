# Live pilot: change impact (affected-test interception + ripple replay)

Arms: `baseline` vs `impact` (PreToolUse rewrite of broad test runs to affected tests; ripple replay at Stop).
Claude Code, claude-sonnet-5-5, 2 reps. $8.1 for 24 new runs.
- Ripple-prone tasks (eval/tasks_ripple: 47b94d424a, 9114355463 MySQL; 930f1a32f7 Postgres; 5e6887adc8 T-SQL):
  both arms run in this pilot (eval-rt-base, eval-rt-imp).
- Complex tasks (2aae7f7605, 6581f8c38b, 66316e335f, 7f1cf60c88): impact runs here (eval-imp-cx), baseline from the
  complex-task study (eval-cx-base-a/b, same harness, one day earlier, two parallel workers vs three here).

| mean per run | ripple tasks: baseline | impact | complex: baseline | impact |
|---|---|---|---|---|
| wall time | 138 s | 110 s (−20%) | 312 s | 228 s (−27%) |
| cost | $0.229 | $0.231 | $0.432 | $0.462 |
| model requests | 13.3 | 12.3 | 20.4 | 20.5 |
| test commands by the agent | 4.6 | 2.4 | 7.5 | 6.9 |
| hidden-test score | 0.928 | 0.929 | 0.985 | 0.985 |
| existing tests broken | 0 | 0 | 0.25 | 0.25 |

- Interception fired in 23 of 24 impact runs. Many intercepted runs fell back to the full suite because the edited
  code also runs at import time (the safety rule from the planted-bug check), which limits the time saved.
- Ripple reports in 4 runs, all judged intended by the agent: T-SQL -> Fabric (the same change correctly inherited;
  false alarm, and the report's 120-character cut hid the difference) and Postgres -> Redshift/Materialize (the reference
  fix leaves the children unchanged; agents kept the change but disclosed it, one correcting an earlier wrong claim).
- The 7f1cf60c88 StarRocks regression occurs in both arms: no existing test input exercises it, so neither selection
  nor replay can see it.
- One outlier (66316e335f impact rep 2: 36 requests, 20 test commands, $0.75) drives the complex-task cost increase.
