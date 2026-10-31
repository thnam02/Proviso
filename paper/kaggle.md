# Proviso: Safe Regression Test Selection for Python Coding Agents

## Abstract

Coding agents validate each edit by running tests, and full suites are slow. Regression test selection (RTS) runs only the affected tests, but existing Python approaches are unsafe on a common pattern: behaviour reached through data built at import time, such as dispatch tables and methods located by constructed names. This paper presents Proviso, an RTS approach for Python that combines per-test function coverage with a comparison of the *values* a package computes at import time, before and after a change. We evaluate it on five projects with 469 planted bugs and 181 real commits, against the tests that actually fail, and in 72 coding-agent runs. Proviso misses a failing test in 3% of test-breaking changes, compared with 17–24% for pytest-testmon and 44–61% for NameRTS. It reduces median test time by 78–91% on loosely coupled projects. In the agent study, Proviso reduces the agent's median task time from 124 s to 71 s with no loss in correctness.

## 1. Introduction

Coding agents check their work by running tests, 8.8 times per SWE-bench task on average [Lin et al. 2026], and on consumer hardware each full-suite run can take minutes. The same study reports that, for Claude Code, forbidding execution reduces token usage by 56–62% with little loss in resolved tasks: execution is costly enough that agents may be better off without it.

Regression test selection (RTS) offers a middle ground by running only the tests a change can affect. An RTS technique should be *effective*, skipping many tests, and *safe*, never skipping a test whose outcome the change alters. For agents, safety is critical: a skipped failing test becomes a regression submitted as correct.

Most RTS research targets statically typed languages [Gligoric et al. 2015; Legunsen et al. 2017]. In Python, dynamic typing makes call graphs incomplete. NameRTS [Wang et al. 2026] avoids call graphs by propagating dependencies through names, and coverage-based tools such as pytest-testmon record which code each test executes. Both share a blind spot: Python libraries often reach behaviour through *data constructed at import time*, such as dispatch tables, operator maps, and methods located by names assembled from strings. A test depending on such data neither executes the code that built it, which ran at import, nor mentions it by name.

Our key insight is that the effect of such a change is observable *as a value*. Importing the package before and after a change and comparing the values it constructs reveals which tables, attributes, and constants changed, and the tests that read them can be selected.

We present Proviso, which combines (i) per-test function coverage for edits inside function bodies, (ii) *import-time snapshot comparison* for all other edits, and (iii) attribution of fixture setup to every test using the fixture, with each test file recorded in a fresh interpreter. Proviso plugs into a coding agent as a shell hook. This paper makes the following contributions:

- Import-time snapshot comparison, a technique that selects tests by the import-time values a change alters, implemented in Proviso, an RTS tool for coding agents.
- A benchmark of 650 changes across five projects with failing-test ground truth, with validated setups of eight baselines including NameRTS and TDAD [Alonso et al. 2026].
- Empirical evidence that data-driven dispatch makes existing Python RTS approaches miss failures, while Proviso misses failures in 3% of test-breaking changes.
- A live agent study showing that safe selection makes a coding agent faster without reducing correctness.

## 2. Motivating Example

sqlglot, a SQL transpiler, generates SQL by dispatching each expression type to a generator method. A simplified illustration, not sqlglot's literal code:

```python
class Generator:
    TRANSFORMS = {exp.SomeExpression: some_handler, ...}  # dispatch table, built at import
    def sql(self, expression):
        handler = getattr(self, f"{expression.key}_sql")  # name assembled at run time
        return handler(expression)

class SQLiteGenerator(Generator):
    def datediff_sql(self, expression): ...              # name appears nowhere else
```

Consider two single-line bugs that break tests: a comparison flipped inside `datediff_sql`, and an entry deleted from the Redshift dialect's `TRANSFORMS`. For the first, NameRTS detects the modified function, but no test refers to the name `datediff_sql`, which exists only as a string assembled at run time; NameRTS selects zero tests. For the second, the modified line is a class body executed at import, so a coverage-based tool sees no test covering it.

Proviso handles both. The failing tests executed `datediff_sql` when the coverage map was recorded. For the table entry, Proviso imports the package before and after the change, finds that the Redshift generator's `TRANSFORMS` differs, and selects the tests that use that generator or a subclass.

## 3. Approach

Proviso operates in two phases: an *analysis phase*, run once per base commit, and a *selection phase*, run on every test command.

### 3.1 Analysis Phase

**Dependency map.** Proviso runs the test suite once under a pytest plugin based on Python 3.12's monitoring API (PEP 669). For each test *t*, it records:
- *F(t)*: the package functions that *t* executes, including code run by its fixtures and by the import of its test module;
- *C(t)*: the package classes on whose instances methods ran, closed under the method resolution order, since subclasses read inherited tables.

A session-scoped fixture is credited to every test that requests it. Each test file is recorded in a separate interpreter, so memoised state cannot hide dependencies. Functions executed while the package is imported form a global set *G*.

**Import-time snapshot.** A subprocess imports every package module and computes a fingerprint for each module-level name and class attribute: recursively for containers and objects, by qualified name for functions and classes, and by bytecode and captured values for lambdas and closures. Seeds are fixed, memory addresses removed, and layout-dependent orderings ignored; loggers are compared by their own settings, and modules generated at install are excluded.

### 3.2 Selection Phase

Proviso maps each changed line in `git diff` to its innermost function or, failing that, to its enclosing class or module. Let *E* be the set of edited functions. A test *t* is selected if any of the following holds:
1. *t* executed an edited function: *F(t) ∩ E ≠ ∅*;
2. *t* reads an import-time value that changed;
3. *t* uses a class whose definition changed.

Rule 2 applies when a change touches class- or module-level code or a function in *G*: Proviso snapshots the working tree and compares it with the base. The *readers* of each changed value are the functions whose source refers to its name, together with their callers, since a reader's result is often cached. A changed class attribute only affects tests whose *C(t)* contains that class or a subclass.

Proviso errs towards running more tests. A new source file selects all tests, tests added or edited by the agent always run, and if *E* alone reaches 90% of the suite's test time, the full suite runs without a snapshot.

### 3.3 Integration with Coding Agents

Proviso installs as a pre-tool hook that rewrites broad test commands (`pytest`, `pytest tests/`) into a Proviso run. Optionally, the agent also receives a *blast-radius report* listing the edited functions, the changed import-time values, the classes inheriting them, and the affected tests.

## 4. Evaluation

We address four research questions:
- **RQ1 (Safety):** How safe is Proviso compared with existing Python RTS approaches?
- **RQ2 (Cost):** How much testing time does Proviso save, including its own overhead?
- **RQ3 (Ablation):** How much do Proviso's channels beyond function coverage contribute?
- **RQ4 (Agents):** Does Proviso make a coding agent faster without reducing correctness, and does the blast-radius report help?

### 4.1 Experimental Setup

**Subjects.** Table 1 lists the projects. Two were held out: pinned before any run, with no change to Proviso's selection logic after their results.

*Table 1: Subject projects.*

| Project | Domain | Tests | Role |
|---|---|---|---|
| sqlglot | SQL transpiler | 1,166 | development |
| sympy (`sympy/functions`) | symbolic mathematics | 581 | development |
| SQLAlchemy (`test/base`, `test/sql`) | database toolkit | 9,761 | development |
| pygments | syntax highlighting | 5,339 | held out |
| datasette | web application | 2,853 | held out |

**Changes.** *Planted bugs* are single-line faults sampled with a fixed seed, 95 per project: flipped comparisons and booleans in function bodies (40), and deleted table entries or flipped flags at class level (30) and module level (25). *Real commits* apply each commit's source changes to its parent, included if the parent's suite runs in our environment. In total, 283 of 469 planted bugs and 76 of 181 commits break at least one test.

**Ground truth.** Unlike prior work that labels the tests executing a modified function as affected [Wang et al. 2026], we use the tests that *actually fail* after the change. A failure counts only if it recurs on re-run. A change that stops the suite from starting breaks every test. Hanging changes (4, in sympy) and tests created by a change are excluded.

**Baselines.** *Name matching* selects tests named after the changed code. *Static imports* selects test files whose transitive imports include a changed module. *File coverage* selects tests that executed a changed file (Ekstazi-style). *pytest-testmon 2.2.0* selects at block level; tests in extension-less files, on which it crashes, count as selected. *NameRTS* runs unmodified; our setup reproduces its published loguru selections on 16 of 17 commits (mean Jaccard 0.996). *TDAD* is run at its default 50-test cap and uncapped.

**Metrics.** A change has a *miss* if any failing test is not selected. *Time share* is the selected tests' time over the full suite's. *End-to-end time* adds Proviso's selection time.

### 4.2 RQ1: Safety

*Table 2: Test-breaking changes with a miss, and mean time share over all changes.*

| Selector | Planted bugs with a miss | Commits with a miss | Time share |
|---|---|---|---|
| Name matching | 243/283 (86%) | 53/76 (70%) | 4% |
| TDAD (default cap)¹ | 229/236 (97%) | 71/75 (95%) | 1% |
| TDAD (uncapped)¹ | 159/236 (67%) | 51/75 (68%) | 47% |
| NameRTS | 125/283 (44%) | 46/76 (61%) | 37% |
| File coverage² | 54/223 (24%) | 19/72 (26%) | 36% |
| pytest-testmon³ | 46/273 (17%) | 18/76 (24%) | 54% |
| Static imports | 37/283 (13%) | 12/76 (16%) | 83% |
| **Proviso** | **8/283 (3%)** | **2/76 (3%)** | 51% |

¹ Out of memory on sympy. ² Not applicable on datasette (incomplete testmon records). ³ Failed to collect on 10 bugs.

Among selectors that skip tests, Proviso has the fewest misses in every project, except two ties and datasette's four breaking commits, where NameRTS misses none and Proviso one. Static imports misses less only on sympy, by running every test. On the held-out projects, Proviso misses in 2 of 116 breaking planted bugs, compared with 29 for testmon and 67 for NameRTS.

**Causes of misses.** Most of NameRTS's misses in sqlglot and SQLAlchemy involve dispatch targets located by constructed names, dispatch and operator table entries, and class-level flags such as `supports_native_boolean = True`. For the `datediff_sql` bug, it selects no test even with both pruning heuristics disabled. Such changes modify no function body, so its reported 99.6% safe rate, measured against tests executing modified functions, does not carry over. It also cannot select pygments' data-file tests. testmon misses in 26 of 56 breaking pygments bugs, whose lexer rules are class-level tables loaded on first use. Proviso's misses come from pure-data classes whose methods never run (3), caching within a test file (3), shared application setup (3), and one sympy test of 143 failures.

**Answer to RQ1:** Proviso misses a failing test in 3% of test-breaking changes, against 17–24% for pytest-testmon and 44–61% for NameRTS; the gap arises mostly from changes to import-time data.

### 4.3 RQ2: Cost

*Table 3: Median end-to-end time per test command, selection included.*

| Project | Planted: full → Proviso | Commits: full → Proviso | Proviso faster |
|---|---|---|---|
| sqlglot | 27.4 → **2.6** s | 31.2 → **4.0** s | 123/147 |
| pygments | 7.9 → **1.7** s | 9.5 → **1.9** s | 116/148 |
| sympy | 58.0 → 47.8 s | 60.5 → **5.5** s | 65/112 |
| datasette | 63.2 → 63.9 s | 64.3 → 53.3 s | 50/119 |
| SQLAlchemy | 24.2 → 26.8 s | 24.5 → 25.7 s | 45/124 |

On sqlglot and pygments, Proviso reduces median end-to-end time by 78–91%. On sqlglot and sympy it is both safer than NameRTS and selects less test time (24% versus 51%, and 57% versus 66%, for planted bugs). On SQLAlchemy and datasette it saves little: a shared compiler reaches most SQLAlchemy tests, and most datasette tests exercise the whole application. Where Proviso is slower, it loses only its selection time (median 0.2–3.4 s). Recording the dependency map takes one suite run per base commit.

**Answer to RQ2:** Proviso reduces median test time by 78–91% on loosely coupled projects; on tightly coupled ones it stays safe by selecting most tests.

### 4.4 RQ3: Ablation

We compare Proviso with two reduced variants: *function coverage* (rule 1 alone) and *function-plus-file* (rule 1, plus, for a change outside function bodies, every test that executed any function in the changed file).

*Table 4: Ablation.*

| Variant | Planted bugs with a miss | Commits with a miss | Time share |
|---|---|---|---|
| Function coverage | 159/283 (56%) | 39/76 (51%) | 16% |
| Function-plus-file | 60/283 (21%) | 6/76 (8%) | 36% |
| Proviso | 8/283 (3%) | 2/76 (3%) | 51% |

Function coverage misses most failures, as 55 of every 95 planted bugs lie outside function bodies. A file-level fallback still misses in 21%, since tables defined in one file are read by functions in others. Snapshot comparison and fixture attribution reduce misses sevenfold, at the cost of selecting more tests.

**Answer to RQ3:** Relative to a file-level fallback, snapshot comparison reduces misses from 21% to 3% of planted bugs.

### 4.5 RQ4: Coding Agents

**Approach.** Claude Code (Claude Sonnet) solved 12 real sqlglot fixes from their base commits, with the issue as the prompt, in three arms with two repetitions each (72 runs): *baseline*, where the agent chooses its own tests; *selection*, where Proviso rewrites broad test commands; and *selection + report*, which adds the blast-radius report. Runs start from a fresh clone with a $1 budget and are graded on the fix's hidden tests, with existing tests as regression checks.

*Table 5: Agent study results (24 runs per arm).*

| | Baseline | Selection | Selection + report |
|---|---|---|---|
| Hidden-test score (mean) | 93.1% | 94.1% | 92.7% |
| Runs breaking an existing test | 0 | 0 | 0 |
| Test commands | 115 | 84 | 93 |
| Task time (median) | 124 s | **71 s** | **73 s** |
| API cost (mean) | $0.218 | **$0.182** | $0.207 |

**Results.** Proviso rewrote test commands in 18 and 19 runs of its two arms. Paired by task (Wilcoxon signed-rank), selection was faster on 10 of 12 tasks (median 44 s saved, *p* = 0.012) and cheaper (*p* = 0.034). With the report, the agent was faster on 9 of 12 tasks (*p* = 0.042) but no cheaper (*p* = 1.0). The agent read the report in 17 runs without scoring higher.

**Answer to RQ4:** Safe test selection reduced the agent's median task time by 43% without reducing its hidden-test score. The blast-radius report provided no additional benefit.

## 5. Threats to Validity

**Internal validity.** Proviso was refined on three development projects; the held-out projects mitigate this. After the first pygments run, we fixed the recorder to include data-file tests, without changing selection logic. A snapshot false alarm (logger state, a generated version module) found during the agent study was fixed after all benchmark results; re-scoring all 650 changes changed no selection. Two earlier agent runs were discarded: Claude Code's `--bare` mode disabled Proviso's hook, then the false alarm caused near-full selection. The baseline arm ran the same day as the Proviso arms, not interleaved. Timings are single runs on one 12-core machine.

**External validity.** We study five Python projects; planted bugs are single-line, and sympy and datasette have few breaking commits (1 and 4). The agent study covers one project, 12 tasks, and one model, and no run broke an existing test, so it cannot show whether selection prevents regressions. Proviso does not model state in files or on the network, tests that inspect code structure, or pure-data classes loaded lazily after import.

## 6. Related Work

**RTS.** Ekstazi [Gligoric et al. 2015] tracks file dependencies dynamically, and STARTS [Legunsen et al. 2017] class dependencies statically. For Python, pytest-testmon and pytest-rts [Kauhanen et al. 2021] use coverage. NameRTS [Wang et al. 2026] propagates names and treats functions executed at import as reachable from all tests. Proviso instead compares import-time values directly.

**Shared state.** PolDet [Gyori et al. 2015] compares heap state reachable from static fields to detect polluting tests; Proviso compares import-time state across versions to select tests. Dependent tests also affect RTS [Lam et al. 2020].

**Testing in coding agents.** TDAD [Alonso et al. 2026] gives agents a static test map, TestPrune [Chen et al. 2026] selects tests from an issue before a patch exists, and Lin et al. [2026] measure the cost of execution in program repair.

## 7. Conclusion

Python libraries reach much of their behaviour through data built at import time, which coverage- and name-based RTS cannot follow. By comparing import-time values, Proviso missed failing tests in 3% of test-breaking changes, against 17–97% for existing approaches, cut median test time by 78–91% on loosely coupled projects, and made a coding agent 43% faster without loss in correctness. Future work includes agent studies on regression-prone tasks and more projects.

**Data availability:** tool, benchmark, baseline setups, and agent study at https://github.com/thnam02/Proviso.

## References

- Alonso, P., Yovine, S., Braberman, V. A. (2026). TDAD: Test-Driven Agentic Development – Reducing code regressions in AI coding agents via graph-based impact analysis. arXiv:2603.17973.
- Chen, Y., Ahmed, T., Jabbarvand, R., Hirzel, M. (2026). Can old tests do new tricks for resolving SWE issues? Proc. ACM Softw. Eng. 3(FSE). https://doi.org/10.1145/3808148
- Gligoric, M., Eloussi, L., Marinov, D. (2015). Practical regression test selection with dynamic file dependencies. ISSTA, 211–222.
- Gyori, A., Shi, A., Hariri, F., Marinov, D. (2015). Reliable testing: detecting state-polluting tests to prevent test dependency. ISSTA.
- Kauhanen, E., Nurminen, J. K., Mikkonen, T., Pashkovskiy, M. (2021). Regression test selection tool for Python in continuous integration process. SANER 2021 (VST workshop), 618–621.
- Lam, W., Shi, A., Oei, R., Zhang, S., Ernst, M. D., Xie, T. (2020). Dependent-test-aware regression testing techniques. ISSTA.
- Legunsen, O., Shi, A., Marinov, D. (2017). STARTS: STAtic regression test selection. ASE (tool demo).
- Lin, Z., Zhu, J., Zhou, M., Wang, X., Sun, Z., Yang, R., Lo, D., Li, L. (2026). To Run or Not to Run: Analyzing the cost-effectiveness of code execution in LLM-based program repair. ISSTA. arXiv:2606.26978.
- Wang, Y., Pradel, M., Liu, Z. (2026). Names are all you need: effective and safe regression test selection for Python. ISSTA. arXiv:2605.25356.
- pytest-testmon. https://testmon.org
