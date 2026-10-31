# Proviso: Safe, Fast Test Feedback for Coding Agents

### Test selection that follows Python's data-driven dispatch, evaluated on 650 changes across five repositories

## Abstract

Coding agents check every edit by running tests; on everyday hardware a full suite takes minutes, and a missed failure means the agent ships a regression it believes is correct. Proviso is a test selector for Python that plugs into an agent's shell. Besides recording the functions each test executes, it compares the values a package builds at import time (dispatch tables, keyword maps, class attributes) before and after a change, since many tests read them without executing the code that built them. We evaluate it on five repositories (two held out) with 469 planted bugs and 181 real commits, against the tests that actually fail.
- **Safety.** Proviso misses a failing test in 8 of 283 test-breaking planted bugs (3%) and in 2 of 76 test-breaking commits (3%). pytest-testmon misses in 17% and 24%, and NameRTS, a recent name-based selector, in 44% and 61%. TDAD, a 2026 selector built for agents, misses in 95–97%.
- **Speed.** With selection time included, a typical test run drops from 27 s to 2 s on sqlglot and from 8 s to 1 s on pygments (median). On tightly coupled code (SQLAlchemy, datasette) Proviso stays safe by running most tests.

We release the tool, the benchmark with ground truth, and validated setups of every baseline.

## 1. Introduction

An agent that fixes a bug edits code, runs tests, reads failures and edits again. Agents average 8.8 test executions per SWE-bench task [Lin et al. 2026], and on the consumer hardware this competition targets, each full-suite run can take minutes. The same study finds that banning execution cuts tokens by 56–62% with little loss in resolved tasks: execution is expensive enough that agents may be better off without it. Regression test selection (RTS) offers a middle way, running only the tests a change can affect. But it is only useful to an agent if it is safe, because a missed failure turns into a shipped regression.

Existing Python selectors have a shared blind spot: **much of a Python library's behaviour is reached through data, not through names or executed lines.**
- sqlglot finds its SQL generator methods at runtime: it lists the class's attributes and maps a name like `datediff_sql` to an expression type.
- SQLAlchemy keeps its SQL operators in a module-level table (`operators.gt: " > "`).
- pygments keeps each language's rules in a class-level table.

Such tables are built at import, before any test runs. A tool that records what a test executes (pytest-testmon) does not see the test read the table. A tool that follows names through the code (NameRTS) finds no name connecting the test to `datediff_sql`, because that name is assembled from a string. In our runs NameRTS selects zero tests for a flipped comparison inside `datediff_sql`.

Proviso closes this gap with one idea, plus two safeguards:
1. **Compare values, not just executed lines.** Proviso imports the package before and after a change and compares everything it computed. Tests that read a changed value are selected. Edits inside function bodies use ordinary per-test function coverage.
2. **Credit shared setup** (pytest fixtures) to every test that uses it, not only the first one that ran it.
3. **Record each test file in a fresh process,** so a cache filled by one test cannot hide another test's dependency.

**Contributions.**
1. **A tool.** Proviso selects tests in about 1–2 s per run, rewrites an agent's broad `pytest` commands, and reports to the agent what its change touched.
2. **A benchmark.** 650 changes across five repositories with failing-test ground truth, plus a pipeline that scores any selector. It includes validated setups of eight baselines, among them NameRTS (reproduced on its own benchmark) and TDAD.
3. **Findings.** Data-driven dispatch defeats name- and coverage-based selection; comparing import-time values fixes it, at a cost set by how tightly the code is coupled.

## 2. Method

Proviso works in two phases. Once per base commit, it records a dependency map and an import-time snapshot. Then, on every test run, it selects tests for the agent's current changes.

### 2.1 Once per base commit: the dependency map

The suite runs once under a pytest plugin built on Python 3.12's low-overhead monitoring API (PEP 669). For each test it records four kinds of dependency.

- **Functions executed.** The package functions the test calls, and the package classes whose methods ran on an instance (with the whole method resolution order, since subclasses read inherited tables).
- **Fixtures.** Each pytest fixture instance the test used, with the code that fixture ran during setup and teardown. A session-scoped fixture runs once, but every test that uses it depends on it.
- **Test-module import.** Code that runs while a test module is imported (e.g. a module-level `parse("…")`) is credited to that module's tests.
- **Isolation.** Each test file is recorded in its own interpreter. Memoised results from one file therefore cannot hide another file's dependencies, and the per-file maps are merged.

Functions that run while the package itself is imported go to a global set. Editing one triggers the snapshot comparison below.

**Import-time snapshot.** A subprocess imports every package module and fingerprints every module-level name and class attribute: recursively for containers and objects, by qualified name for functions and classes, by bytecode and captured values for lambdas and closures. Seeds are fixed, addresses stripped, and values whose order depends on memory layout are compared without order.

### 2.2 Every run: select

Each changed line in `git diff` is assigned to its innermost function, or else to class or module level. A test is selected if any of the following holds:
- it executed an edited function, directly or through a fixture or its module's import;
- it reads an **import-time value that actually changed.** For class- or module-level edits, and edits to functions run at import, Proviso snapshots the working tree and compares it with the base. If nothing changed (a comment, an unused constant), nothing more is selected. Otherwise the readers of each changed value are the functions whose source names it, plus their callers, since a reader's result is often cached. A changed class attribute counts only for tests using that class or a subclass;
- it uses a class whose definition changed.

**Safety rules**, always erring towards running more:
- a new source file selects everything;
- tests the agent added or edited always run;
- if edited functions alone already reach 90% of the suite's test time, the full suite runs at once and the snapshot is skipped.

### 2.3 In the agent

Proviso installs as a pre-tool hook. A broad test command (`pytest`, `pytest tests/`) is rewritten into a Proviso run; narrow commands are left alone. Alongside the results, the agent receives a short **blast-radius report**: the functions it edited, the import-time values that changed (grouped by class, with the classes that inherit them), and the affected tests per file.

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
- **Real commits.** Each commit's source changes are applied to its parent, and the parent's tests are run. A commit counts only if the parent's suite runs in our environment: older history stops running past a point, because of Python and dependency versions.

In total: 469 planted bugs, of which 283 break tests (24,543 failing tests), and 181 real commits, of which 76 break tests (135 failing tests).

**Ground-truth hygiene.**
- A failure counts only if it recurs when the failing tests' files are re-run. This dropped up to 9 flaky failures per repository, e.g. a pygments test that writes a fixed `/tmp` path and races with parallel runs.
- A bug after which the suite cannot start counts as breaking every test.
- Bugs on which the suite hangs (4, all in sympy) are left out.
- Tests created by the change itself cannot be selected by anyone, so they are excluded.

**Baselines.**
- *Name-matched tests*: tests named after the changed code, what agents pick by hand.
- *Static imports*: test files whose transitive imports include a changed module.
- *File coverage*: tests that executed a changed file (Ekstazi-style).
- *pytest-testmon 2.2.0*: block-level dynamic RTS, its own selection. It crashes on test files without an extension (33 in pygments), so we exclude those files from its runs and count their tests as always selected.
- *NameRTS* [Wang et al. 2026]: name-based reachability, run unmodified. Through our setup it reproduces its published loguru selections on 16 of 17 commits (mean Jaccard 0.996).
- *TDAD* [Alonso et al. 2026]: graph-based impact analysis for agents, at its default 50-test cap and uncapped.
- *Function coverage*: tests that executed an edited function. This is Proviso without its other channels, an ablation.

**Metrics.**
- A change has a **miss** if any failing test is not selected.
- **Time share** is selected test time over the suite's.
- **End-to-end time** is what one test command costs the agent, in plain seconds: Proviso's selection time plus its selected tests, against the full suite.

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
- **Names built at runtime.** sqlglot dispatches to `<expression>_sql` methods found by listing class attributes. For a flipped comparison in `datediff_sql`, NameRTS detects the changed element, marks all 57 test files as affected at file level, then selects none after name propagation. Disabling both of its pruning heuristics changes nothing. Most of its misses in sqlglot and SQLAlchemy are such dispatch targets, or entries in dispatch and operator tables.
- **NameRTS's own ground truth.** Its 99.6% safety in its own evaluation is measured against tests that execute a modified function. A table entry or class flag modifies no function, yet tests fail.
- **Lazily loaded data.** pygments keeps each lexer's rules in a class-level table, loaded the first time the lexer is requested. testmon misses failures in 26 of 56 breaking planted bugs there.
- **Incomplete coverage records.** On datasette, testmon's per-test records link project code to only about 250 of 2,939 tests. testmon compensates by re-running most tests; selection built directly on those records misses every planted bug.
- **Function coverage alone** (Proviso's ablation) misses in 56% of planted bugs; the other channels close most of the gap.

**Why Proviso misses.** Pure-data classes no method of which runs (sympy, 2 bugs; a lazily loaded pygments lexer, 1 commit); caching inside a test file (SQLAlchemy, 3 bugs, 14 tests); shared application setup and tests that inspect code structure (datasette, 2 bugs, 1 commit); one test of 143 failures (sympy).

### 4.2 Test time and end-to-end run time

Median plain seconds per test command, selection included:

| Repository | Planted: full suite → Proviso | Real commits: full → Proviso | Proviso faster on | Selection time (median) |
|---|---|---|---|---|
| sqlglot | 27.4 → **2.1** | 31.2 → **4.0** | 123 of 147 | 0.9–1.1 s |
| pygments (held out) | 7.9 → **1.1** | 9.5 → **1.5** | 118 of 148 | 1.0–1.2 s |
| sympy | 58.0 → 47.0 | 60.5 → **5.3** | 70 of 112 | 0.1–2.3 s |
| datasette (held out) | 63.2 → 63.2 | 64.3 → 53.2 | 70 of 119 | 0.2–1.0 s |
| SQLAlchemy | 24.2 → 26.1 | 24.5 → 25.9 | 45 of 124 | 1.9 s |

On loosely coupled libraries Proviso cuts a typical run by 84–92%. On tightly coupled code it is safe but saves little.
- In SQLAlchemy, a shared compiler and connection layer reaches most tests.
- In datasette, most tests send HTTP requests through the whole application.

Where Proviso is slower, it selects almost the whole suite and loses at most its selection time (about 2 s).

**What this means for an agent.** At 8.8 test runs per task, the median savings correspond to about 4 minutes per task on sqlglot, 70 s on pygments and 8 minutes on sympy's real commits. This is an estimate: it assumes broad test commands, the ones Proviso intercepts.

### 4.3 Overhead

Recording the dependency map runs the suite once per base commit, with one interpreter per test file. The first selection of a session also builds the base snapshot; later selections take the medians above.

## 5. Limitations and threats to validity

- **Development repositories favour Proviso.** It was refined on sqlglot, sympy and SQLAlchemy. The held-out repositories guard against this, with one disclosure: after the first pygments run, we fixed the recorder to record tests collected from data files. It had recorded none of pygments' 1,508 such tests. The selection logic was unchanged, and datasette saw no change at all.
- **Planted bugs are single-line.** Real-commit evidence is thin for sympy (1 breaking commit) and datasette (4).
- **Remaining blind spots:** pure-data classes loaded lazily after import, tests that inspect code structure, and state in files or the network.
- **Speed depends on coupling.** We report SQLAlchemy and datasette as they are.
- **No live agent study.** The agent-level estimate combines published execution counts with our measured times.
- **Timing:** one 12-core machine.

## 6. Related work

- **Dynamic RTS.** Ekstazi [Gligoric et al. 2015] selects tests by the files they touched. pytest-testmon and pytest-rts bring coverage-based selection to Python. A coverage-based Python tool missed 16–24% of mutants at line level [Kauhanen et al. 2021]. All of these record what tests execute, so values computed at import are invisible to them.
- **Static and Python-specific RTS.** STARTS [Legunsen et al. 2017] follows class dependencies. NameRTS [Wang et al. 2026] propagates names, isolates test files and treats import-time functions as reachable by all tests; Proviso shares the isolation but records execution and compares import-time *values*.
- **Shared state.** PolDet [Gyori et al. 2015] diffs the heap reachable from static fields to detect tests that pollute state. Proviso diffs import-time state across versions to select tests. Dependent tests affect RTS too [Lam et al. 2020].
- **Agents and tests.** TDAD [Alonso et al. 2026] gives agents a static test map; TestPrune [2025] picks regression tests from the issue before a patch exists; Lin et al. [2026] measure what execution costs agents. Proviso targets safe, cheap feedback after each edit.

## 7. Conclusion

Python libraries reach much of their behaviour through data built at import: dispatch tables, operator maps, rule tables, names assembled from strings. Name-based and coverage-based selectors cannot follow it. Comparing import-time values, crediting fixtures and isolating caches gives a selector that missed a failing test in 3% of test-breaking changes across five repositories, against 17% to 97% for existing tools. It cuts typical test runs by 84–92% on loosely coupled code, and stays safe, though slower, where everything is connected. For agents on everyday hardware, that makes running the right tests cheap enough to do after every edit. Code, benchmark and baseline setups: https://github.com/thnam02/Proviso

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
