# Proviso: Safe, Fast Test Feedback for Coding Agents

### Test selection that follows Python's data-driven dispatch, evaluated on 650 changes and with a live coding agent

## Abstract

Coding agents check every edit by running tests; a full suite takes minutes on everyday hardware, and a missed failure ships a regression. Proviso is a Python test selector that plugs into an agent's shell. Besides recording the functions each test executes, it compares the values a package builds at import time (dispatch tables, class attributes) before and after a change, since tests read them without executing the code that built them. We evaluate it on five repositories (two held out) with 469 planted bugs and 181 real commits, against the tests that actually fail, and in 72 Claude Code runs.
- **Safety.** Proviso misses a failing test in 8 of 283 test-breaking planted bugs (3%) and in 2 of 76 test-breaking commits (3%). pytest-testmon misses in 17% and 24%, NameRTS (ISSTA 2026) in 44% and 61%, and TDAD, built for agents, in 95–97%.
- **Speed.** With selection time included, a typical test run drops from 27 s to 3 s on sqlglot and from 8 s to 2 s on pygments (median). On tightly coupled code (SQLAlchemy, datasette) Proviso stays safe by running most tests.
- **Agents.** With Proviso, the agent finished in a median 71 s instead of 124 s, faster on 10 of 12 tasks, with no loss in hidden-test score. A report of what its change touched did not help further.

## 1. Introduction

Agents average 8.8 test executions per SWE-bench task [Lin et al. 2026], and on consumer hardware each full-suite run can take minutes. The same study finds that banning execution cuts tokens by 56–62% with little loss in resolved tasks: execution is expensive enough that agents may be better off without it. Regression test selection (RTS) offers a middle way, running only the tests a change can affect, but only if it is safe: a missed failure becomes a shipped regression.

Existing Python selectors have a shared blind spot: **much of a Python library's behaviour is reached through data, not through names or executed lines.**
- sqlglot finds its SQL generator methods at runtime: it lists the class's attributes and maps a name like `datediff_sql` to an expression type.
- SQLAlchemy keeps its SQL operators in a module-level table (`operators.gt: " > "`).
- pygments keeps each language's rules in a class-level table.

Such tables are built at import, before any test runs. A tool that records what a test executes (pytest-testmon) does not see the test read the table. A tool that follows names (NameRTS) finds no name connecting a test to `datediff_sql`, which is assembled from a string; it selects zero tests for a flipped comparison inside it.

Proviso closes this gap with one idea, plus two safeguards:
1. **Compare values, not just executed lines.** Proviso imports the package before and after a change and compares everything it computed. Tests that read a changed value are selected. Edits inside function bodies use ordinary per-test function coverage.
2. **Credit shared setup** (pytest fixtures) to every test that uses it, not only the first one that ran it.
3. **Record each test file in a fresh process,** so a cache filled by one test cannot hide another test's dependency.

**Contributions.**
1. **A tool.** Proviso selects tests in about 1–3 s per run and rewrites an agent's broad `pytest` commands.
2. **A benchmark.** 650 changes across five repositories with failing-test ground truth, and validated setups of eight baselines, among them NameRTS (reproduced on its own benchmark) and TDAD.
3. **Findings.** Data-driven dispatch defeats name- and coverage-based selection; comparing import-time values fixes it, at a cost set by how tightly the code is coupled. In a live agent study, safe selection makes the agent faster; an impact report does not.

## 2. Method

### 2.1 Once per base commit: the dependency map

The suite runs once under a pytest plugin built on Python 3.12's monitoring API (PEP 669), recording per test:

- **Functions executed.** The package functions the test calls, and the package classes whose methods ran on an instance (with the whole method resolution order, since subclasses read inherited tables).
- **Fixtures.** Each pytest fixture instance the test used, with the code that fixture ran during setup and teardown.
- **Test-module import.** Code that runs while a test module is imported (e.g. a module-level `parse("…")`) is credited to that module's tests.
- **Isolation.** Each test file is recorded in its own interpreter, so memoised results cannot hide another file's dependencies.

Functions that run while the package itself is imported go to a global set. Editing one triggers the snapshot comparison below.

**Import-time snapshot.** A subprocess imports every package module and fingerprints every module-level name and class attribute: recursively for containers and objects, by qualified name for functions and classes, by bytecode and captured values for lambdas and closures. Seeds are fixed, addresses stripped, and layout-dependent orderings ignored; loggers are compared by their own settings, and modules generated at install are skipped.

### 2.2 Every run: select

Each changed line in `git diff` is assigned to its innermost function, or else to class or module level. A test is selected if any of the following holds:
- it executed an edited function, directly or through a fixture or its module's import;
- it reads an **import-time value that actually changed.** For class- or module-level edits, and edits to functions run at import, Proviso snapshots the working tree and compares it with the base. Otherwise the readers of each changed value are the functions whose source names it, plus their callers, since a reader's result is often cached. A changed class attribute counts only for tests using that class or a subclass;
- it uses a class whose definition changed.

**Safety rules**, always erring towards running more:
- a new source file selects everything;
- tests the agent added or edited always run;
- if edited functions alone already reach 90% of the suite's test time, the full suite runs at once and the snapshot is skipped.

### 2.3 In the agent

Proviso installs as a pre-tool hook that rewrites broad test commands (`pytest`, `pytest tests/`) into a Proviso run. Optionally, the agent also receives a **blast-radius report**: the functions it edited, the import-time values that changed (grouped by class, with the classes that inherit them), and the affected tests per file.

## 3. Benchmark

**Repositories.** Three were used during development, and two were held out: pinned before any run, with no change to Proviso's selection logic after their results.

| Repository | Kind | Tests | Role |
|---|---|---|---|
| sqlglot | SQL parser and transpiler | 1,166 | development |
| sympy (`sympy/functions`) | symbolic mathematics | 581 | development |
| SQLAlchemy (`test/base`, `test/sql`) | database toolkit | 9,761 | development |
| pygments | syntax highlighter; most tests are data files | 5,339 | held out |
| datasette | web application on SQLite | 2,853 | held out |

**Changes.**
- **Planted bugs**: 95 per repository, sampled with a fixed seed. They are single-line changes: flipped comparisons and booleans in function bodies (40), deleted table entries and flipped flags at class level (30) and at module level (25). Ground truth is the full suite run on the bugged tree.
- **Real commits.** Each commit's source changes are applied to its parent, whose tests are run. A commit counts only if the parent's suite runs in our environment (older history breaks on Python and dependency versions).

In total: 469 planted bugs, of which 283 break tests (24,543 failing tests), and 181 real commits, of which 76 break tests (135 failing tests).

**Ground-truth hygiene.**
- A failure counts only if it recurs when its test file is re-run (up to 9 flaky failures dropped per repository).
- A bug after which the suite cannot start counts as breaking every test.
- Bugs on which the suite hangs (4, all in sympy) are left out.
- Tests created by the change itself are excluded.

**Baselines.**
- *Name-matched tests*: tests named after the changed code.
- *Static imports*: test files whose transitive imports include a changed module.
- *File coverage*: tests that executed a changed file (Ekstazi-style).
- *pytest-testmon 2.2.0*: block-level dynamic RTS, its own selection. It crashes on extension-less test files (33 in pygments); their tests count as always selected.
- *NameRTS* [Wang et al. 2026]: name-based reachability, run unmodified. Through our setup it reproduces its published loguru selections on 16 of 17 commits (mean Jaccard 0.996).
- *TDAD* [Alonso et al. 2026]: graph-based impact analysis for agents, at its default 50-test cap and uncapped.
- *Function coverage*: tests that executed an edited function (Proviso's ablation).

**Metrics.**
- A change has a **miss** if any failing test is not selected.
- **Time share** is selected test time over the suite's.
- **End-to-end time**: Proviso's selection time plus its selected tests, against the full suite.

## 4. Results

### 4.1 Safety

| Selector | Planted bugs with a miss (of 283) | Real commits with a miss (of 76) | Test time run (mean) |
|---|---|---|---|
| Name-matched tests | 243 (86%) | 53 (70%) | 3% |
| TDAD (default cap)¹ | 229 of 236 (97%) | 71 of 75 (95%) | 1% |
| TDAD (uncapped)¹ | 159 of 236 (67%) | 51 of 75 (68%) | 48% |
| Function coverage (ablation) | 159 (56%) | 39 (51%) | 23% |
| NameRTS | 125 (44%) | 46 (61%) | 39% |
| File coverage | 60 (21%) | 6 (8%) | 41% |
| pytest-testmon² | 46 of 273 (17%) | 18 (24%) | 56% |
| Static imports | 37 (13%) | 12 (16%) | 83% |
| **Proviso** | **8 (3%)** | **2 (3%)** | **52%** |

¹ TDAD's test linking ran out of memory on sympy (over 23 GB). ² testmon could not collect tests on 10 planted bugs that break the package's import.

Among selectors that skip part of the suite, Proviso misses the fewest failures in every repository (datasette's four breaking commits are a tie). Static imports matches it on sympy and SQLAlchemy only by running all of their tests. On the held-out repositories, Proviso misses in 2 of 116 breaking planted bugs, against 29 for testmon and 67 for NameRTS.

**Why the others miss.**
- **Names built at runtime.** sqlglot dispatches to `<expression>_sql` methods found by listing class attributes. For the `datediff_sql` bug, NameRTS detects the changed element, then selects no test after name propagation, even with both pruning heuristics disabled. Most of its misses in sqlglot and SQLAlchemy are such dispatch targets, or entries in dispatch and operator tables.
- **NameRTS's own ground truth.** Its 99.6% safety in its own evaluation is measured against tests that execute a modified function. A table entry or class flag modifies no function, yet tests fail.
- **Lazily loaded data.** pygments keeps each lexer's rules in a class-level table, loaded the first time the lexer is requested. testmon misses failures in 26 of 56 breaking planted bugs there.
- **Incomplete coverage records.** On datasette, testmon's records link project code to only about 250 of 2,939 tests, so it re-runs most tests.
- **Function coverage alone** (Proviso's ablation) misses in 56% of planted bugs; the other channels close most of the gap.

**Why Proviso misses.** Pure-data classes no method of which runs (sympy, 2 bugs; a lazily loaded pygments lexer, 1 commit); caching inside a test file (SQLAlchemy, 3 bugs, 14 tests); shared application setup and tests that inspect code structure (datasette, 2 bugs, 1 commit); one test of 143 failures (sympy).

### 4.2 Test time and end-to-end run time

Median plain seconds per test command, selection included:

| Repository | Planted: full suite → Proviso | Real commits: full → Proviso | Proviso faster on | Selection time (median) |
|---|---|---|---|---|
| sqlglot | 27.4 → **2.6** | 31.2 → **4.0** | 123 of 147 | 1.4–1.5 s |
| pygments (held out) | 7.9 → **1.7** | 9.5 → **1.9** | 116 of 148 | 1.6 s |
| sympy | 58.0 → 47.8 | 60.5 → **5.5** | 65 of 112 | 0.2–3.4 s |
| datasette (held out) | 63.2 → 63.9 | 64.3 → 53.3 | 50 of 119 | 0.2–1.8 s |
| SQLAlchemy | 24.2 → 26.8 | 24.5 → 25.7 | 45 of 124 | 2.1–2.6 s |

On loosely coupled libraries Proviso cuts a typical run by 78–91%. On tightly coupled code it is safe but saves little.
- In SQLAlchemy, a shared compiler and connection layer reaches most tests.
- In datasette, most tests send HTTP requests through the whole application.

Where Proviso is slower, it selects almost the whole suite and loses its selection time (2–3 s).

Recording the dependency map runs the suite once per base commit, one interpreter per test file.

### 4.3 Live agent study

**Setup.** Claude Code (Claude Sonnet) solved 12 real sqlglot fixes from their base commits, with the issue as the prompt. Three arms, two repetitions each, 72 runs: *baseline* (the agent runs whatever tests it chooses), *selection* (Proviso rewrites its broad test commands, no report) and *selection + report* (the blast-radius report as well). Each run starts from a fresh clone, capped at $1. Grading uses the fix's hidden tests, with existing tests as regression checks.

| | Baseline | Selection | Selection + report |
|---|---|---|---|
| Hidden-test score (mean) | 93.1% | 94.1% | 92.7% |
| Runs breaking an existing test | 0 | 0 | 0 |
| Test commands | 115 | 84 | 93 |
| Wall time (median) | 124 s | **71 s** | **73 s** |
| API cost (mean) | $0.218 | **$0.182** | $0.207 |

Proviso narrowed a test command in 18 and 19 of the 24 runs of its two arms. Paired by task (Wilcoxon signed-rank, 12 tasks), selection was faster on 10 of 12 tasks (median 44 s saved, p = 0.012) and cheaper (p = 0.034). With the report it was faster on 9 of 12 (p = 0.042) and no cheaper (p = 1.0): the agent read the report in 17 runs and spent tokens on it, without a better score. The time saved matches the full-suite runs avoided (about 1.5 per baseline run, 25 s each). On these tasks Proviso selected a median of 51% of the tests (5–18% on six tasks; all of them on two, where the edited functions run in 98% of the test time).

**Disclosures.** Two earlier attempts were discarded. In the first, Claude Code's `--bare` mode ignored Proviso's hook, so it never ran. In the second, a false alarm in the import-time snapshot (logger state, and a version module generated at install) made Proviso select nearly every test. After the fix, both Proviso arms were rerun; the baseline arm was rerun the same day, a few hours later, rather than interleaved.

## 5. Limitations and threats to validity

- **Development repositories favour Proviso.** The held-out repositories guard against this, with one disclosure: after the first pygments run, we fixed the recorder to include tests collected from data files (it had missed all 1,508). Selection logic was unchanged.
- **Planted bugs are single-line.** Real-commit evidence is thin for sympy (1 breaking commit) and datasette (4).
- **Remaining blind spots:** pure-data classes loaded lazily after import, tests that inspect code structure, and state in files or the network.
- **Speed depends on coupling.** We report SQLAlchemy and datasette as they are.
- **A change after the held-out runs.** The snapshot fix found in the agent study came after all benchmark results. Re-scoring all 650 changes with it changed no selection; its timings are reported.
- **The agent study is small:** one repository, 12 tasks, one model, arms not interleaved. No run in any arm broke an existing test, so it cannot show whether selection prevents regressions.
- **Timing:** one 12-core machine, single runs.

## 6. Related work

- **Dynamic RTS.** Ekstazi [Gligoric et al. 2015] selects tests by the files they touched. pytest-testmon and pytest-rts bring coverage-based selection to Python. A coverage-based Python tool missed 16–24% of mutants at line level [Kauhanen et al. 2021]. All of these record what tests execute, so values computed at import are invisible to them.
- **Static and Python-specific RTS.** STARTS [Legunsen et al. 2017] follows class dependencies. NameRTS [Wang et al. 2026] propagates names and treats import-time functions as reachable by all tests; Proviso records execution and compares import-time *values*.
- **Shared state.** PolDet [Gyori et al. 2015] diffs the heap reachable from static fields to detect tests that pollute state. Proviso diffs import-time state across versions to select tests. Dependent tests affect RTS too [Lam et al. 2020].
- **Agents and tests.** TDAD [Alonso et al. 2026] gives agents a static test map; TestPrune [2025] picks regression tests from the issue before a patch exists; Lin et al. [2026] measure what execution costs agents. Proviso targets safe, cheap feedback after each edit.

## 7. Conclusion

Python libraries reach much of their behaviour through data built at import, which name- and coverage-based selectors cannot follow. Comparing import-time values, crediting fixtures and isolating caches gives a selector that missed a failing test in 3% of test-breaking changes across five repositories, against 17% to 97% for existing tools. It cuts typical test runs by 78–91% on loosely coupled code, and stays safe, though slower, where everything is connected. In a live study it made a coding agent finish a median 43% faster with no loss in correctness; telling the agent what its change touched added nothing. For agents on everyday hardware, safe selection makes running the right tests cheap enough to do after every edit. Code, benchmark and baseline setups: https://github.com/thnam02/Proviso

## References

- Alonso, P., Yovine, S., Braberman, V. (2026). TDAD: Test-Driven Agentic Development. arXiv:2603.17973.
- Gligoric, M., Eloussi, L., Marinov, D. (2015). Practical regression test selection with dynamic file dependencies. ISSTA.
- Gyori, A., Shi, A., Hariri, F., Marinov, D. (2015). Reliable testing: detecting state-polluting tests to prevent test dependency. ISSTA.
- Kauhanen, E., Nurminen, J. K., Mikkonen, T., Pashkovskiy, M. (2021). Regression test selection tool for Python in continuous integration process. SANER (VST workshop).
- Lam, W., Shi, A., Oei, R., Zhang, S., Ernst, M. D., Xie, T. (2020). Dependent-test-aware regression testing techniques. ISSTA.
- Legunsen, O., Shi, A., Marinov, D. (2017). STARTS: STAtic regression test selection. ASE (tool demo).
- Lin, Z., et al. (2026). To Run or Not to Run: Analyzing the cost-effectiveness of code execution in LLM-based program repair. ISSTA. arXiv:2606.26978.
- TestPrune: Can old tests do new tricks for resolving SWE issues? (2025). arXiv:2510.18270.
- Wang, Y., Pradel, M., Liu, Z. (2026). Names are all you need: effective and safe regression test selection for Python. In Proc. ISSTA 2026. arXiv:2605.25356.
- pytest-testmon. https://testmon.org
