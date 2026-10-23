# Proviso: Safe, Fast Test Feedback for Coding Agents

### Test selection that sees import-time state, and a benchmark of 75 test-breaking changes

## Abstract

Coding agents check every patch by running tests. On everyday hardware, rerunning a full suite after each edit is slow, and the shortcut agents take instead, running the test file named after the module they edited, misses failures. We present Proviso, a test-selection tool that plugs into an agent's shell. It records which functions each test runs and, unlike coverage-based selectors, also compares the values a package computes while it is imported (dispatch tables, keyword maps, class attributes), which no test executes but many tests read. It then orders the selected tests so a failure surfaces first. On 75 changes that break tests in sqlglot and sympy (16 real commits, 59 planted bugs; 1,424 failing tests), Proviso selects every failing test. NameRTS, a recent name-based selector, misses failures in 24 changes, and pytest-testmon in 11. On 54 real sqlglot commits, Proviso runs 27% of the suite's test time on average (median 10%). With ranking, an agent sees its first failure after ⟦TBD⟧ seconds (median, selection included), against ⟦TBD⟧ seconds for a normal test run. We release the tool, the benchmark with ground truth and per-test times, and a verified setup of the two baselines.

## 1. Introduction

An agent that fixes a bug edits code, runs the tests, reads the failures, and edits again. The test run is the agent's only ground truth, and it sits inside the loop: a fix that takes ten iterations pays for ten test runs. On a cloud machine that cost is small. On the consumer hardware the Gemma 4 Developer Agent Competition targets, a full suite can take minutes, while the model is waiting.

Agents cope by running fewer tests, usually the file named after the module they edited (`tests/test_parser.py` for `parser.py`). This is cheap and unsafe: on our benchmark, choosing tests by name misses failures in 50 of 75 changes that break tests (Section 5). A missed failure is the expensive error for an agent, because it submits a patch it believes is correct.

Regression test selection (RTS) is the standard answer: run only the tests whose dependencies changed. Dynamic RTS tools record what each test executes and select tests that executed changed code (Ekstazi for Java; pytest-testmon for Python). Static tools follow imports or names (NameRTS). Both have a blind spot in Python. Much of a Python library's behaviour lives in values computed once, while the package is imported: dispatch tables, keyword maps, registries, class attributes built from other classes. sqlglot, a SQL parser, reaches most of its parser methods through tables such as

```python
FUNCTION_PARSERS = {"JSON_TABLE": lambda self: self._parse_json_table(), ...}
```

A test that parses `JSON_TABLE` never executes the line that builds this table; it runs at import, before any test. A tool that records executed lines therefore sees no link between the test and the table. A name-based tool sees the test mention no parser method. Edit the table and both tools skip the tests that break.

Proviso closes this gap with one idea: instead of asking which tests executed a changed line, ask which values the change altered, by importing the package before and after and comparing everything it computed. Tests that read an altered value are selected. For edits inside function bodies, ordinary per-test function coverage suffices.

**Contributions.**
1. **A tool.** Proviso combines per-test function coverage with an import-time state comparison, ranks the selected tests so failures surface early, and drops into an agent's shell by rewriting broad `pytest` commands. Selection takes about 3 s per run after a one-off setup.
2. **A benchmark.** 75 test-breaking changes with ground-truth failing tests, 67 further real changes for selection size, per-test times, and a setup of NameRTS and pytest-testmon verified against published results.
3. **Findings.** Function coverage alone misses failures in 51 of 75 changes; adding the import-time comparison misses none while selecting less than file-level fallbacks. Ordering the selection reduces the agent's wait for its first failure by ⟦TBD⟧× (median).

## 2. Method

Proviso works in two phases: once per base commit (the commit the agent starts from) it records a coverage map and an import-time snapshot; on every test run it selects and orders tests for the agent's current changes.

### 2.1 Once per session: coverage map and base snapshot

**Coverage map.** The test suite runs once with a pytest plugin that records, per test, the package functions it calls (file and first line), the package classes whose methods ran on an instance (including the instance type's whole method resolution order, since a subclass reads inherited tables), whether the test started a subprocess (then it always runs), and its duration. Functions that run outside any test, during imports or collection, go to a global set; editing one selects the full suite. For packages that memoise results across tests (sympy's `@cacheit`), the cache is cleared before each test so each test records what it really depends on.

The recorder uses Python 3.12's low-overhead monitoring API (PEP 669). A plain function is reported once per test and then switched off until the next test; only package methods stay on, to see the classes they run on. On sqlglot's 1,104 tests this records an identical map to a `sys.setprofile` recorder at 44% less overhead (recording run 147 s against 217 s; plain run 58 s).

**Import-time snapshot.** A subprocess imports every package module and fingerprints every module-level name and class attribute: recursively for containers and objects, by qualified name for functions and classes, by bytecode and captured values for lambdas and closures built at import. Sources of noise are removed: random generators get fixed seeds, memory addresses are stripped, cached hashes are ignored, and values whose order depends on memory layout (a tuple built from a set of classes) are detected by importing the base twice more with the heap shifted, and compared without order.

### 2.2 Every run: select

From `git diff` against the base, each changed line is assigned to the innermost function containing it, or else to module or class level.

- **Function edits** select the tests whose coverage includes the function.
- **Module- and class-level edits**, and edits to functions that run at import, trigger a new snapshot of the working tree, which is compared with the base snapshot. If nothing changed (a comment, an unused constant), nothing more is selected. Otherwise Proviso finds the readers of each changed value: functions whose source mentions its name, plus their callers, because a reader's result is often computed once and cached, after which only its caller runs. A changed class attribute counts only in tests that use that class or a subclass. Tests that call a reader, or whose own source names the value, are selected.
- **Structural changes** a value comparison cannot see are handled conservatively: a class whose bases change, or that gains an attribute matching a computed lookup in the code (`getattr(self, f"{key}_sql")`), is treated as edited; a new source file selects everything.

Tests the agent added or edited always run.

### 2.3 Every run: order

The selected tests run in this order: tests the agent wrote or edited, then those that ran a changed function (ranked by how many changed functions they ran), then the rest; fastest first within each group. If the agent's command stops at the first failure (`-x` or `--maxfail`), Proviso passes that on, so the order decides how soon the agent hears about a broken patch. Otherwise the whole selection runs and the order changes nothing.

### 2.4 In the agent

Proviso installs as a pre-tool hook. When the agent runs a broad test command (`pytest`, `pytest tests/`), the hook rewrites it into a Proviso run; narrow commands the agent writes itself are left alone. The run reports which tests were selected and why, and the failures. Per-commit caches (base snapshot, source indexes, test-file names) keep each selection to the cost of one snapshot of the working tree.

## 3. Benchmark

**Repositories.** sqlglot (a SQL parser and transpiler for 30+ dialects with deep class inheritance; 1,104 tests) and sympy (symbolic mathematics with memoisation and generated rule tables; the `sympy/functions` tests for planted bugs, each task's subpackage tests for real fixes).

**Changes.**
- *Real sqlglot commits (54).* Each commit's source changes are applied to its parent, and the parent's tests are run. Tests that fail there are the ground truth, typically the old versions of tests the commit had to update. 16 commits break tests (39 failing tests).
- *Real sympy fixes (13).* None breaks an existing test; they measure selection size.
- *Planted bugs (125).* Single-line bugs: flipped comparisons and booleans in functions, deleted table entries and flipped flags at class and module level, inherited methods overridden with a flipped condition. 96 in sqlglot at two commits (42 break tests, 593 failing tests); 29 in sympy (17 break tests, 792 failing tests). Ground truth is the full suite on the bugged tree.

In total, 75 changes break tests, with 1,424 failing tests. For every change we store the ground truth and per-test times, and the benchmark scores any selector given as a function from a changed tree to a set of tests.

**Baselines.**
- *Name-matched test files*: `test_<module>.py`, what agents and developers pick by hand.
- *Static import graph*: test files whose transitive imports include a changed module.
- *File-level coverage*: tests that executed a line of a changed file (Ekstazi-style).
- *pytest-testmon 2.2.0*: block-level dynamic RTS for Python, its own selection.
- *NameRTS*: static selection by name reachability (Wang, Pradel and Liu, 2026), from its replication package with dependencies pinned to its environment. Our setup reproduces its published selections on the first six evaluated commits of its dataset exactly.

Two setup details changed results and are documented. sympy's configuration passes `-m`, which silently turns testmon's selection off; we drop the same slow tests at collection instead. NameRTS selects test files; a selected file counts as all its tests.

**Metrics.** A change has a *miss* if any failing test (or a test module that fails to load) is not selected. *Time share*: selected test time over the suite's. *Time to first failure*: wall time from the agent's command until the first failing test finishes, in plain (untraced) seconds, including selection.

## 4. Results

### 4.1 Safety

| Selector | Changes with a missed failure (of 75) | Failing tests missed (of 1,424) |
|---|---|---|
| Name-matched test files | 50 | 1,352 |
| Proviso, functions only (ablation) | 51 | 927 |
| NameRTS | 24 | 69 |
| pytest-testmon | 11 | 235 |
| Static import graph | 10 | 15 |
| File-level coverage | 10 | 164 |
| Proviso, file fallback (ablation) | 10 | 168 |
| **Proviso** | **0** | **0** |

Proviso is the only selector without a miss on any dataset. The misses of the others trace back to import-time state:

- **Data changes.** Real commit `efbc5e220c` only adds entries to `Postgres.TIME_MAPPING`, a class-level table. No test executes a line of that file while running, so testmon selects one test and misses both failures. Proviso finds the changed table, in Postgres and through inheritance in Redshift, Materialize and RisingWave, and selects the 56 tests that read it.
- **Code run while test modules import.** A flipped loop condition in `Parser._parse_with` breaks 37 test modules that parse SQL at import; testmon misses all 37. Proviso knows the function runs at import and selects the full suite.
- **Inheritance.** A new override in `Spark2Parser` breaks a Databricks test; the Databricks test never executed `spark2.py`, so coverage-based tools miss it.
- **String-keyed dispatch.** NameRTS misses failures in 23 of 42 breaking sqlglot planted bugs: tests reach parser methods through keyword tables, and name no method.
- **Generated rule tables.** Most of testmon's sympy misses are edits to `assumptions_generated.py`, read only at import.

The ablations isolate the idea. Function coverage alone misses failures in 51 of 75 changes. Falling back to every test of the edited file repairs most of that but still misses failures in 10 changes and selects 60% of test time on real sqlglot commits. The import-time comparison closes all remaining misses and selects 27%.

### 4.2 Test time

Share of the suite's test time selected (mean, median in brackets):

| Changes | Proviso | NameRTS | pytest-testmon |
|---|---|---|---|
| 54 real sqlglot commits | **27% (10%)** | 75% (99%) | 61% (99.6%) |
| 13 real sympy fixes | **34% (13%)** | 57% (62%) | 40% (19%) |
| 96 planted bugs, sqlglot | 20% (4%) | 36% (1%) | 18% (2%) |
| 29 planted bugs, sympy | 56% (93%) | 58% (100%) | 36% (4%) |

On real commits Proviso selects the least of the three. Where the others select less, on planted bugs, they miss failures: testmon selects 36% of sympy test time but misses failures in 5 of 17 breaking bugs. sympy is Proviso's weakest case. Its large functions and widely read rule tables make many changes reach most tests, so Proviso's advantage there is safety, not size.

### 4.3 Time to first failure

⟦TBD: end-to-end table, plain seconds, selection time included: full suite default order; full suite fastest first; Proviso ranked. Report median, mean, and how often each is fastest.⟧

From traced times (profiler on, so ratios only), ordering matters as much as selection: Proviso's selection in pytest's order finds the first failure after 0.9% of the suite's time (median), and after 0.2% when ranked. The full suite run fastest-first needs 3.0%. Most of the gain from ordering comes from running fast tests first. Ranking by changed functions adds a further improvement on real sqlglot commits (median 0.7% against 1.4%) and none on planted bugs.

### 4.4 Overhead

- **Recording the coverage map:** once per base commit; 147 s on sqlglot against a 58 s plain run (2.5×).
- **First selection of a session:** about 15 s (three base snapshots, source indexes).
- **Every later selection:** median ⟦TBD⟧ s when import-time state must be compared (47 of 54 real commits), 0.1 s otherwise.

⟦TBD: break-even, total time per run: selection + selected tests vs full suite.⟧

## 5. Limitations and threats to validity

- **Two repositories, both Python.** sqlglot is also where Proviso was developed, which favours it. sympy was not, and is its weakest case on selection size.
- **Granularity.** NameRTS and file-level coverage select files, testmon selects tests through blocks, Proviso selects tests. Finer granularity helps Proviso on test time, not on safety.
- **Planted bugs are single-line.** Real-change safety rests on 16 sqlglot commits with 39 failing tests.
- **Dynamic behaviour outside the snapshot.** State created lazily after import (on first use) is covered only through per-test coverage of the code that creates it, and environment-dependent behaviour (files, network) is not compared.
- **No agent study yet.** We measure the test loop, not end-to-end agent success. An agent study with a local model (Gemma 4) is future work.

## 6. Related work

- **Dynamic RTS.** Ekstazi (Gligoric et al., 2015) selects tests by the files they touched; pytest-testmon brings block-level coverage to Python. Both record what tests execute, so values computed at import are invisible to them.
- **Static RTS.** STARTS (Legunsen et al., 2017) and import-graph tools follow class or module dependencies; NameRTS (Wang, Pradel and Liu, 2026) follows names, which suits Python's dynamic dispatch but not dispatch through string-keyed tables.
- **Test prioritisation.** Ordering tests to find faults early is classical (Rothermel et al., 2001; Elbaum et al., 2002). We apply it to the agent loop and measure the agent's wait including selection.
- **Agents and tests.** SWE-bench (Jimenez et al., 2024) uses fail-to-pass and pass-to-pass tests to judge agent patches; agents themselves rely on the tests they choose to run, which is where selection fits.

## 7. Conclusion

A Python package's import-time state is a large, invisible dependency of its tests. Comparing it before and after a change gives test selection that missed no failure on 75 test-breaking changes, where every existing selector missed some, while running about a quarter of the suite's time on real commits. With ranking, a coding agent learns that its patch broke something within seconds. Proviso and the benchmark are open source: ⟦repo link⟧.

## References

- Elbaum, S., Malishevsky, A. G., Rothermel, G. (2002). Test case prioritization: a family of empirical studies. IEEE TSE.
- Gligoric, M., Eloussi, L., Marinov, D. (2015). Practical regression test selection with dynamic file dependencies. ISSTA.
- Jimenez, C. E., et al. (2024). SWE-bench: Can language models resolve real-world GitHub issues? ICLR.
- Legunsen, O., Shi, A., Marinov, D. (2017). STARTS: STAtic regression test selection. ASE (tool demo).
- Rothermel, G., Untch, R. H., Chu, C., Harrold, M. J. (2001). Prioritizing test cases for regression testing. IEEE TSE.
- Wang, ?, Pradel, M., Liu, ? (2026). Names Are All You Need: Effective and Safe Regression Test Selection for Python. arXiv:2605.25356.
- pytest-testmon. https://testmon.org
