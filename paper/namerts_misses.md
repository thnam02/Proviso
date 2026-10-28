# Why NameRTS misses failing tests in our evaluation (28 Oct 2026)

## 1. Is our NameRTS setup valid? Yes.
We ran NameRTS through our own setup (research/v2/namerts_driver.py, called as the pipeline calls it) on the
first 20 target commits of NameRTS's published loguru benchmark (results/namerts_repro/loguru.jsonl).

| Measure | Result |
|---|---|
| Selection identical to NameRTS's published one | 16 of 17 commits (the other 2 select nothing in both) |
| Mean overlap (Jaccard) with the published selection | 0.996 |
| Safe against NameRTS's ground truth | 18 of 19 for our setup; 19 of 19 for the published runs |

The single difference: 3 test files that likely fail to collect in our environment (e.g. test_type_hinting.py needs
typing plugins). One commit could not be checked out.

## 2. What causes the misses
Data: the select rows for sqlglot and SQLAlchemy, plus three bugs reproduced locally on sqlglot.

**(a) Dynamic dispatch through constructed names: confirmed.**
- Bug: sqlglot/generators/sqlite.py:328, `==` → `!=` inside `SQLiteGenerator.datediff_sql`.
- NameRTS detects the modified element (one changed checksum). Its file-level stage marks all 57 test files as
  affected; its name-based stage then selects 0.
- Turning off both pruning heuristics (PRUNE_CRITICAL_FUNCTIONS, PRUNE_NAME_RESOLUTION) still selects 0, so pruning is
  not the cause.
- Cause: sqlglot builds its dispatch table at runtime from `dir(cls)`, mapping `<expr>_sql` names to expression
  classes (`_build_dispatch` in generator.py). The name `datediff_sql` is never written anywhere except its definition,
  so name propagation has no path from any test to it.
- Proviso and the simple "ran the changed function" rule both select the failing test (tests/dialects/test_sqlite.py),
  because they record execution.

**(b) Dispatch tables (dicts from tokens or expression types to functions/lambdas): strongly indicated.**
- Bug: a TRANSFORMS entry in sqlglot/generators/redshift.py (delete). Change detected; NameRTS selects 0 test files.
- The same pattern appears in all 10 sqlglot class/module-kind misses (parser token tables, TRANSFORMS, type maps) and
  in SQLAlchemy's compiler operator tables (`operators.gt: " > "` etc., 8 module-kind misses).
- A parser-method flip (sqlglot/parser.py, `_match_set` condition) also selected 0. Parser methods are reached through
  class-level tables of lambdas.

**(c) Class-attribute flags read through `self.<attr>` (SQLAlchemy): not yet inspected individually.**
- 9 class-kind misses, e.g. `supports_native_boolean = True`, `isinsert = False`, `inherit_cache = True`; NameRTS
  often selects 0.

**(d) Tests that are data files (pygments): a design limit.**
- NameRTS selects `.py` test files, so pygments' 1,508 golden-output tests (from .txt and example files) can never be
  selected. This accounts for its 56/56 planted-bug misses there.

## 3. Counts by bug kind (changes where NameRTS missed a failing test)

| Repo | class (data in class bodies) | module (module-level tables) | function (bodies; often dynamically dispatched) |
|---|---|---|---|
| sqlglot | 9 | 1 | 15 |
| SQLAlchemy | 9 | 8 | 9 |

## 4. Why this differs from NameRTS's paper (99.6% safe)
1. **Ground truth.** NameRTS's is "test files that execute a modified function" (instrumented, plus references to
   global variables). Ours is "tests that actually fail". Data-table and class-attribute changes modify no function
   body, so they rarely count as affecting tests under its definition, yet they break tests.
2. **Change population.** Planted bugs hit data tables and dispatch targets uniformly. Real commits in NameRTS's 10
   projects may touch them less often.
3. **Subjects.** sqlglot and SQLAlchemy are dispatch-heavy (auto-discovered generator methods, token tables, operator
   tables); pygments keeps its tests as data files.

## 5. Use in the paper
- A validity check: the reproduction above shows the baseline is configured correctly.
- A finding: name-based static propagation cannot follow data-driven dispatch (dispatch tables, names constructed at
  runtime, class-level data), which is common in Python libraries. Proviso records execution and compares
  import-time state, so it catches these.
- Still to do: inspect two or three SQLAlchemy class-attribute cases (category c), and count how many of NameRTS's
  misses fall into each category across all repos.
