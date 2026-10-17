# Ripple regressions in sqlglot's history

`mine.py` replays the same probes (inputs from the existing tests, each run in its own dialect and in every dialect
that inherits from it) at every first-parent commit and compares consecutive commits. A *divergent ripple* is a child
dialect output that changed at commit P differently from the parent's output on the same input. `label.py` labels them.

| window | commits | divergent | child's own files untouched | later restored |
|---|---|---|---|---|
| HEAD~799..HEAD (Jun–Oct 2026) | 800 | 166 | 75 (36 commit x child groups) | 4 (one group) |
| HEAD~1599..HEAD~800 | 800 | 50 | 35 (19 groups) | 3 (one group, a revert) |

Automatic labels (crash / cosmetic / declared unsupported / newly parses / changed, "lossy" when words of the reference
output are lost) narrow the list; the final call is manual. Clear regressions (child untouched by the commit):

| commit | parent -> child | effect | fixed later? |
|---|---|---|---|
| ba0bff3d91 jsonpath falsey union members | presto -> trino, dune | `JSON_EXTRACT(x, '$["a",""]')` raises ValueError | no |
| efbc5e220c postgres TO_CHAR tokens | postgres -> redshift, materialize, risingwave | format `'DD Mon YYYY HH:MI AM'` becomes `'DD TMMon YYYY HH12:MI p.m.'` | reverted (8ae227476d) |
| 5d997d94d8 bare ALTER TABLE DROP | mysql -> doris | `DROP b, DROP view` rewritten to `DROP COLUMN ...` | restored |
| 7f1cf60c88 optional ALTER actions | mysql -> doris | `KEY_BLOCK_SIZE=8` becomes `'KEY_BLOCK_SIZE'=8` | no |
| 9114355463 nameless constraints | mysql -> starrocks | `CONSTRAINT PRIMARY KEY (a)` silently dropped | no |
| 862fd55467 trino temporal precision | presto -> athena, dune | `TIMESTAMP` becomes `TIMESTAMP(0)` (parent unchanged) | no |
| 4ada15a429 robust ON CONFLICT | postgres -> materialize | `ON CONFLICT ... DO UPDATE` silently dropped, no unsupported warning | no |
| a313c8bee1 boolean update assignments | postgres -> materialize | `ON CONFLICT ... DO UPDATE` silently dropped | no |
| d7fd83a7dc START WITH tokenisation | postgres -> redshift | `CREATE VIEW start WITH (...)` loses `WITH` | no |

Takeaway: maintainers of a well-tested library introduce silent ripple regressions regularly (about one clear case
every ~180 commits here) and almost never notice: 7 of 9 are still present at the newest commit.
