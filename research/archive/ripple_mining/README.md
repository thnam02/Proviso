# Ripple regressions in sqlglot's history

`mine.py` replays the same probes (inputs from the existing tests, each run in its own dialect and in every dialect
that inherits from it) at every first-parent commit and compares consecutive commits. A *divergent ripple* is a child
dialect output that changed at commit P differently from the parent's output on the same input. `label.py` labels them.

| window | commits | divergent | child's own files untouched | later restored |
|---|---|---|---|---|
| HEAD~799..HEAD (Jun–Oct 2026) | 800 | 166 | 75 (36 commit x child groups) | 4 (one group) |
| HEAD~1599..HEAD~800 | 800 | 50 | 35 (19 groups) | 3 (one group, a revert) |

Automatic labels (crash / cosmetic / declared unsupported / newly parses / changed, "lossy" when words of the reference
output are lost) narrow the list; the final call is manual.

## Correction after auditing against pre-existing child behaviour

A first manual pass listed 9 "clear regressions". Checking how each child handled the nearest form that already worked
at the commit's base showed that 5 of them are pre-existing limitations of the child that the new syntax merely reaches
(the commit made the input parse; the child then treats it as it already treated similar inputs):

| commit | child | at the base commit the child already... |
|---|---|---|
| 4ada15a429, a313c8bee1 | materialize | drops every `ON CONFLICT ... DO UPDATE` clause, also simple ones |
| d7fd83a7dc | redshift | drops `WITH` from any `CREATE VIEW v WITH (...)` |
| 7f1cf60c88 | doris | writes table options as `PROPERTIES ('KEY_BLOCK_SIZE'=8)` (quoted keys are Doris syntax) |
| ba0bff3d91 | trino, dune | raises ValueError on any multi-member union path such as `'$["a","b"]'` |
| 9114355463 | starrocks | drops a table-level `PRIMARY KEY (a)` (found by the agent in the smoke run) |

One more (862fd55467, athena/dune follow Trino's deliberate precision change) is plausibly intended. Regressions that
the commit itself caused, on inputs whose child output was already valid:

| commit | parent -> child | effect | caught by a human? |
|---|---|---|---|
| efbc5e220c postgres TO_CHAR tokens | postgres -> redshift, materialize, risingwave | `'DD Mon YYYY HH:MI AM'` becomes `'DD TMMon YYYY HH12:MI p.m.'` | reverted (8ae227476d) |
| 5d997d94d8 bare ALTER TABLE DROP | mysql -> doris | `DROP b, DROP view` rewritten to `DROP COLUMN ...` | restored later |

Takeaway (revised): in 1,600 commits of a well-tested library, commit-caused silent ripple regressions are rare (2, both
caught by maintainers within weeks). Most child/parent divergences on new syntax are pre-existing child limitations;
reporting them is disclosure, not prevention. The "changed from base" criterion is fooled whenever the input did not
parse before, so ground truth needs the analog check above.
