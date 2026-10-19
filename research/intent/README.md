# Intent check: does a patch change behaviour the task did not ask for?

Proviso's behavioural diff of a patch (behaviour.py): import-time values that changed (table entries, flags), and
outputs that changed on ~15,000 SQL inputs from sqlglot's tests plus the fix's own new tests, each run in its dialect
and in every dialect inheriting from it. An LLM judge (judge.py; no tools) gets the task and one view of the patch
-- code diff, behavioural diff, or both -- and answers clean / unintended.

Cases (build.py): 54 real sqlglot fixes (intended changes; should be judged clean) and 214 versions of them with one
planted bug in a file the fix touched (comparison/boolean flips, deleted table entries, flipped flags).

```
tasks 54; planted bugs 214: observable 183, no effect on outputs/import state 31
  observable & caught by tests 156, observable & silent 27; no effect but caught by tests 8
  fixes with an empty behavioural diff: 5

| judge | view | bugs flagged (observable) | silent bugs flagged | caught bugs flagged | fixes flagged (false alarm) | unparsed | cost |
|---|---|---|---|---|---|---|---|
| existing tests | - | 156/183 | 0/27 | 156/156 | 0/54 | - | - |
| claude-haiku-5-5 | behaviour | 174/183 | 24/27 | 150/156 | 11/54 | 2 | $0.43 |
| claude-haiku-5-5 | both | 181/183 | 27/27 | 154/156 | 19/54 | 1 | $0.59 |
| claude-haiku-5-5 | code | 181/183 | 26/27 | 155/156 | 12/54 | 0 | $0.44 |
| claude-sonnet-5-5 | behaviour | 171/183 | 23/27 | 148/156 | 8/54 | 0 | $5.01 |
| claude-sonnet-5-5 | both | 182/183 | 27/27 | 155/156 | 13/54 | 0 | $6.97 |
| claude-sonnet-5-5 | code | 181/183 | 26/27 | 155/156 | 11/54 | 0 | $5.05 |
```

Findings
- The judge flags almost every planted bug with an observable effect, including the 27 that no existing test catches
  (tests: 0/27). From the behavioural diff alone it flags 93-95% of them without seeing any code.
- Planted bugs do not separate the views: they appear in the code diff as stray edits next to the fix (only 5 of 183
  lie inside the fix's own lines), so reading the code already finds ~99%. Whether behavioural facts catch side effects
  that code reading misses needs real agent patches (rebuildable from the saved transcripts).
- The behavioural view raises the fewest alarms on the real fixes (Sonnet 8/54, Haiku 11/54, vs 11-19/54 with code).
  Some alarms are real behaviour changes that the task text did not state: commit 03c96cbbfd removes MySQL
  `NOT SOUNDS LIKE` (it parsed before, it raises ParseError since, still at sqlglot HEAD); the commit message says
  this is deliberate ("not valid MySQL syntax"), the task description given to the judge does not.
- Coverage limit: 31 of 214 planted bugs leave no trace in the behavioural diff (the inputs exercise parsing and
  generation only); 8 of those are caught by tests.
