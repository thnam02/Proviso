# Proviso vs existing test selectors

Every selector is scored on the same changes, against the same ground truth, with the same per-test times.

## Selectors (rts.py)

| selector | what it is |
|---|---|
| Retest all | every test (reference) |
| Name-matched test files | test files named after a changed module (`test_<module>.py`, or `test_<subpackage>.py`): how developers and agents usually pick tests by hand |
| Static import graph | test files whose transitive imports include a changed module (file-level static RTS, as in pytest-incremental) |
| File-level coverage | tests whose recorded coverage executed a line of a changed file (file-level dynamic RTS, Ekstazi-style); per-test file sets from pytest-testmon's database |
| pytest-testmon | pytest-testmon 2.2.0 with coverage.py 7.10.7 (C tracer), its own selection: database built at the base commit, then a collect-only run on the changed tree |
| ... (cache cleared) | sympy only: the testmon database recorded with sympy's cache cleared before each test, as Proviso's coverage maps are (otherwise a test that reuses a cached result records no dependency on the code that computed it) |
| Proviso, functions only | ablation: tests whose base coverage calls a changed function; changes outside function bodies ignored |
| Proviso, file fallback | ablation: functions only, plus every test calling any function of a file changed outside function bodies |
| Proviso | dc_engine.impact.selection (function coverage + import-time state comparison) |

A change that adds a source file selects everything in all coverage-based selectors.

## Changes and ground truth

- **Planted bugs**: single-line bugs (comparison/boolean flips in functions, deleted table entries or flipped flags at class and
  module level, inherited methods overridden with a flip), ground truth = the full suite on the bugged tree
  (research/ripple/mutants.py, research/sympy/mutants_sympy.py). sqlglot: 96 bugs at two commits; sympy: 29 bugs in
  sympy/functions and sympy/core, scored on the sympy/functions tests (one bug whose suite hangs is left out).
- **Real changes, sqlglot** (prep_sqlglot_real.py): 54 merged commits (the task commits of the earlier studies). The parent
  tree gets the commit's source changes (not its test changes) and the parent's tests are run; tests failing there and
  not at the parent are the ground truth (typically the old version of tests the commit had to update). 16 of the 54
  break existing tests.
- **Real changes, sympy** (run_sympy_real.py): the 13 fixes of research/sympy, universe = the task's subpackage tests.
  None breaks an existing test, so these measure selection size only.

Test time = per-test time from the coverage run (profiler on; only ratios are used). "Changes with a missed failure" counts
changes that break tests where at least one failing test (or a test module that fails to load) was not selected.

## Headline

Pooled over the 75 changes that break existing tests (1,424 failing tests):

| selector | changes with a missed failure | failing tests missed |
|---|---|---|
| Proviso, functions only | 51 of 75 | 927 |
| Name-matched test files | 50 of 75 | 1,352 |
| NameRTS (Wang, Pradel, Liu 2026) | 24 of 75 | 69 |
| pytest-testmon | 11 of 75 | 235 |
| Static import graph | 10 of 75 | 15 |
| File-level coverage | 10 of 75 | 164 |
| Proviso, file fallback | 10 of 75 | 168 |
| **Proviso** | **0 of 75** | **0** |

Share of test time selected (mean, median in brackets):

| changes | Proviso | NameRTS | pytest-testmon |
|---|---|---|---|
| 54 real sqlglot commits | **27% (10%)** | 75% (99%) | 61% (99.6%) |
| 13 real sympy fixes | **34% (13%)** | 57% (62%) | 40% (19%) |
| 96 planted bugs, sqlglot | 20% (4%) | 36% (1%) | 18% (2%) |
| 29 planted bugs, sympy | 56% (93%) | 58% (100%) | 36% (4%) |

- **Proviso is the only selector with no miss on any dataset.**
- **On real commits, it selects the least of the coverage-based tools.** On sqlglot it selects less than NameRTS on 35 of 54
  commits (more on 19).
- **Where the others select less, they miss failures.** On planted sympy bugs, testmon selects 36% but misses failures in 5 of 17
  bugs. NameRTS is safe there, but at 58%.
- **NameRTS misses most on sqlglot planted bugs** (23 of 42), where parsers are reached through tables keyed by SQL keywords
  (`FUNCTION_PARSERS = {"JSON_TABLE": lambda self: self._parse_json_table()}`) that name reachability cannot follow.

What the ablations show:

- **Coverage of functions alone is unsafe** (51 of 75 changes with a miss): many bugs live in tables and flags evaluated at import.
- **Falling back to the whole file for such changes repairs most of that, but costs precision.** On real sqlglot commits it
  selects 60% of the time and still misses failures in 10 changes.
- **Comparing import-time state instead closes the remaining misses and cuts selection to 27%.**

## NameRTS setup (namerts_driver.py, run_namerts.py)

- **Tool:** NameRTS from its replication package (github.com/ZJU-CTAG/NameRTS @ f1acdae), driven through its own classes in
  the order of its evaluation script. Dependencies are at the versions in its environment_313.yml (tree-sitter 0.24.0,
  tree-sitter-python 0.23.6, xxhash 3.5.0), built from source; conda is replaced by a stand-in that runs the command directly.
- **Fidelity:** on the first 6 evaluated loguru commits of its dataset, our setup reproduces the paper's published
  selections exactly (6/6 identical; check_namerts_fidelity.py, results/namerts_fidelity_loguru.json).
- **One runtime fix to NameRTS:** a test file that imports nothing from the project crashed it; such a file now depends on
  itself only, as its code comment intends.
- **Scope on sympy:** NameRTS's test files are limited to the subpackage tests the comparison scores; its dependency
  analysis still covers the whole tree.
- **Isolated workers:** 2 (the paper: 30-50). For 3 of the 13 sympy fixes (matrices, polys), the 7 GB machine ran out
  of memory with 2 workers, so those use 1 worker. With 1 worker NameRTS runs without per-file isolation, the
  configuration the paper used for pylint.
- **Granularity:** NameRTS selects test files; a selected file counts as all its tests.

## pytest-testmon on sympy: `-m` turns its selection off

sympy's pytest config adds `-m 'not slow and not tooslow'`, and testmon 2.2.0 deactivates its selection whenever -m is
used. As shipped, testmon therefore runs every sympy test. The rows above use testmon with its selection active
(fix_sympy_testmon.py: `-o addopts= -p noslow`, a plugin dropping the same slow tests at collection).

## Why the others miss

- **Data changes**: real commit efbc5e220c only adds entries to `Postgres.TIME_MAPPING`, a class-level table. Tests never
  execute a line of that file while running (the table is built at import), so file coverage and testmon select one
  test and miss both failures. Proviso's import-state comparison finds the changed tables (Postgres, and through
  inheritance Redshift, Materialize, RisingWave) and selects the 56 tests that read them.
- **Code that runs while a test module is imported**: a flipped `while True` in `Parser._parse_with` breaks 37 test
  modules that parse SQL at import. Coverage recorded per test never attributes import-time execution to a test;
  testmon misses all 37. Proviso knows the function runs at import (coverage map `__global__`) and selects the full suite.
- **Inheritance**: a new override in `Spark2Parser` breaks a Databricks test (Databricks inherits from Spark2). The
  Databricks test never executed `spark2.py` at the base, so file coverage and testmon miss it; Proviso sees the
  class gained a method and selects tests using the class or its subclasses.
- **Dynamic imports**: sqlglot loads dialects by name, so the static import graph cannot see that a dialect test
  depends on a dialect module (9 of 42 planted changes missed).
- **Generated tables (sympy)**: most sympy planted bugs testmon and file coverage miss are edits to
  `sympy/core/assumptions_generated.py`, a table of assumption rules read at import; no test executes a line of it
  while running (testmon misses failures in 5 of 17 planted bugs; 4 with sympy's cache cleared while recording).
- **String-keyed dispatch (NameRTS)**: sqlglot reaches most parser and generator methods through class-level tables
  keyed by SQL keywords or expression types; the test names none of those methods, so name reachability does not
  connect it to them (23 of 42 planted sqlglot changes missed).

## Tables

### sqlglot, planted changes: 96 changes, 42 break existing tests (593 failing tests)

| selector | changes with a missed failure | failing tests missed | tests selected | test time selected (median) |
|---|---|---|---|---|
| Retest all | 0 of 42 | 0 of 593 | 100.0% | 100.0% (100.0%) |
| Name-matched test files | 29 of 42 | 562 of 593 | 3.3% | 6.9% (0.5%) |
| Static import graph | 9 of 42 | 13 of 593 | 52.4% | 49.1% (17.8%) |
| File-level coverage | 5 of 42 | 11 of 593 | 28.4% | 25.0% (6.4%) |
| pytest-testmon | 5 of 42 | 80 of 593 | 17.3% | 18.2% (2.4%) |
| NameRTS | 23 of 42 | 68 of 593 | 36.7% | 36.2% (0.8%) |
| Proviso, functions only | 31 of 42 | 142 of 593 | 3.8% | 4.7% (0.0%) |
| Proviso, file fallback | 5 of 42 | 15 of 593 | 18.6% | 18.6% (2.6%) |
| Proviso | 0 of 42 | 0 of 593 | 18.7% | 20.4% (3.7%) |

### sqlglot, real changes: 54 changes, 16 break existing tests (39 failing tests)

| selector | changes with a missed failure | failing tests missed | tests selected | test time selected (median) |
|---|---|---|---|---|
| Retest all | 0 of 16 | 0 of 39 | 100.0% | 100.0% (100.0%) |
| Name-matched test files | 7 of 16 | 17 of 39 | 11.0% | 33.7% (4.3%) |
| Static import graph | 1 of 16 | 2 of 39 | 96.3% | 96.3% (100.0%) |
| File-level coverage | 1 of 16 | 2 of 39 | 73.7% | 69.0% (99.6%) |
| pytest-testmon | 1 of 16 | 2 of 39 | 62.7% | 61.1% (99.6%) |
| NameRTS | 1 of 16 | 1 of 39 | 69.4% | 75.3% (99.3%) |
| Proviso, functions only | 7 of 16 | 13 of 39 | 18.9% | 20.9% (5.7%) |
| Proviso, file fallback | 1 of 16 | 2 of 39 | 61.3% | 59.5% (99.7%) |
| Proviso | 0 of 16 | 0 of 39 | 30.7% | 27.3% (9.8%) |

### sympy, planted changes: 29 changes, 17 break existing tests (792 failing tests)

| selector | changes with a missed failure | failing tests missed | tests selected | test time selected (median) |
|---|---|---|---|---|
| Retest all | 0 of 17 | 0 of 792 | 100.0% | 100.0% (100.0%) |
| Name-matched test files | 14 of 17 | 773 of 792 | 1.5% | 1.3% (0.0%) |
| Static import graph | 0 of 17 | 0 of 792 | 100.0% | 100.0% (100.0%) |
| File-level coverage | 4 of 17 | 151 of 792 | 42.2% | 52.2% (78.6%) |
| File-level coverage (cache cleared) | 4 of 17 | 151 of 792 | 44.0% | 54.0% (83.0%) |
| pytest-testmon | 5 of 17 | 153 of 792 | 30.3% | 35.6% (4.0%) |
| pytest-testmon (cache cleared) | 4 of 17 | 151 of 792 | 31.5% | 37.0% (4.0%) |
| NameRTS | 0 of 17 | 0 of 792 | 58.4% | 58.4% (100.0%) |
| Proviso, functions only | 13 of 17 | 772 of 792 | 3.6% | 3.8% (0.0%) |
| Proviso, file fallback | 4 of 17 | 151 of 792 | 31.6% | 37.0% (4.0%) |
| Proviso | 0 of 17 | 0 of 792 | 51.0% | 55.7% (92.7%) |

### sympy, real changes: 13 changes, 0 break existing tests (0 failing tests)

| selector | changes with a missed failure | failing tests missed | tests selected | test time selected (median) |
|---|---|---|---|---|
| Retest all | 0 of 0 | 0 of 0 | 100.0% | 100.0% (100.0%) |
| Name-matched test files | 0 of 0 | 0 of 0 | 25.2% | 28.5% (19.9%) |
| Static import graph | 0 of 0 | 0 of 0 | 92.4% | 92.8% (100.0%) |
| File-level coverage | 0 of 0 | 0 of 0 | 36.6% | 55.0% (51.8%) |
| File-level coverage (cache cleared) | 0 of 0 | 0 of 0 | 37.1% | 55.1% (51.8%) |
| pytest-testmon | 0 of 0 | 0 of 0 | 22.7% | 40.4% (18.6%) |
| pytest-testmon (cache cleared) | 0 of 0 | 0 of 0 | 23.1% | 40.5% (18.6%) |
| NameRTS | 0 of 0 | 0 of 0 | 51.6% | 56.5% (62.1%) |
| Proviso, functions only | 0 of 0 | 0 of 0 | 18.5% | 34.1% (13.3%) |
| Proviso, file fallback | 0 of 0 | 0 of 0 | 23.1% | 40.4% (18.6%) |
| Proviso | 0 of 0 | 0 of 0 | 18.5% | 34.1% (13.3%) |


## Limitations

- Two Python codebases. Name-matched and static-import selectors are our implementations of the usual rules;
  file-level coverage is derived from testmon's per-test records, not from Ekstazi (which is Java).
- Planted bugs are single-line. Real-change safety rests on 16 commits with 39 failing tests (sqlglot only).
- Overhead (building coverage maps, import-state snapshots) is not yet measured.

## Reproduce

prep_sqlglot_real.py (per commit: testmon database, ground truth, testmon and Proviso selections), run_sqlglot_real.py,
run_planted.py sqlglot 7f1cf60c88 / 862fd55467, run_planted.py sympy, run_sympy_real.py [--testmon], analyze.py.
NameRTS: run_namerts.py planted-sqlglot COMMIT / planted-sympy / real-sqlglot / real-sympy; testmon on sympy:
fix_sympy_testmon.py planted|real. Results: results/*.json (one row per change and selector), results/summary.json.
