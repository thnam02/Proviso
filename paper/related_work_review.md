# Proviso: literature review and novelty check (28 Oct 2026)

Purpose: decide what Proviso can honestly claim as new, what it must cite as prior work, and what reviewers will raise.
Method: about 35 targeted searches plus reading the key papers (abstracts, and the full text where accessible). This is not a
full systematic review; the gaps are listed at the end.

## 1. Bottom line

| Proviso element | Closest prior work | Verdict |
|---|---|---|
| **A. Import-time state: diff the *values* built at import, then select the tests that read changed names** | NameRTS treats import-time functions as one shared key (all tests); Java class-level RTS tracks static-initializer *code*; FineEkstazi compares static-initializer changes as *metadata*; PolDet diffs static-field *values*, but to detect polluting tests, not to select tests | **Likely novel: the strongest claim.** No work found that selects tests by comparing import-time/static state values across versions. |
| **B. Fixtures: dynamic, per-instance attribution of fixture setup code to the tests that use it** | NameRTS adds injected fixture *names* statically; pytest-rts and testmon use per-test coverage contexts (setup attribution not documented) | **Partly novel / incremental.** Worth stating, not the headline. |
| **C. Cached state: record each test file in a fresh process** | NameRTS already does this (pytest-xdist, one process per file); VMVM, PolDet and dependent-test work study shared state | **Not novel.** Cite it as an adopted practice. |
| Blast-radius report for the agent | TDAD gives agents a grep-able test map; RETRACE checks patch-issue alignment with an LLM | Mildly novel as presentation; unevaluated. |
| "Test selection for AI coding agents" | TDAD (2026), TestPrune (2025), To Run or Not to Run (ISSTA 2026) | Gap exists for *safe, dynamic, post-edit* selection, but **no agent study yet**, which is the main weakness. |
| Evaluation design (held-out repos, flaky check, end-to-end incl. selection time, failing-test ground truth) | NameRTS: 10 repos / 500 commits, "affected tests" ground truth; RTSCheck framework | Rigorous, but **smaller scale than NameRTS** (5 repos). |

**Implication:** lead with channel A, framed as "the import-time state problem in Python RTS". Present B as a supporting
mechanism, and C as standard practice (cite NameRTS).

## 2. Related work by group

### 2.1 Classic RTS (mostly Java)
- **Ekstazi** (Gligoric, Eloussi, Marinov, ISSTA 2015): dynamic class/file-level dependencies; the de-facto safe baseline.
  Class-level tracking covers static initializers as code dependencies.
- **STARTS** (Legunsen et al., ASE 2017 tool; FSE 2016 study): static class-level RTS; static RTS can be unsafe (reflection).
- **Reflection-aware static RTS** (Shi et al., OOPSLA 2019): fixes static-RTS misses due to reflection.
- **RTSCheck** (Zhu et al., 2019): framework for finding safety violations in RTS tools. Relevant to our evaluation methodology.
- **FineEkstazi / FineSTARTS** (Liu, Zhang, Nie, Gligoric, Legunsen, ISSTA 2023): ignore semantics-preserving change kinds;
  41.7% fewer tests than Ekstazi. Reasons about change metadata, not runtime values.
- **uRTS** (ICSE 2023): RTS for code *and configuration* changes. Relevant to "non-code dependencies".
- **Predictive Test Selection** (Machalica et al., Facebook, ICSE-SEIP 2019): ML-based, explicitly unsafe; industrial contrast.
- Surveys to cite: Yoo & Harman (2012); Engström et al. (2010).

### 2.2 RTS for Python and dynamic languages
- **NameRTS** (Wang, Pradel, Liu, ISSTA 2026, arXiv 2605.25356): the closest prior work and the main competitor.
  - Name-based dependency propagation, at file and function level.
  - Evaluated on 10 projects (including sympy) and 500 commits: SafeR 99.6%, TimeR 45.6%.
  - Import-time functions go under a shared key, so changing one selects all tests.
  - Per-file process isolation; injected fixture names; no eval/exec.
  - It states that no function-level RTS had been designed specifically for Python before.
  - **Its ground truth is "affected tests" (instrumented modified functions), not failing tests.** This matters: in our runs
    NameRTS misses failing tests far more often than its reported 99.6%. We must explain the difference: the ground-truth
    definition, data-file tests in pygments, and our setup at f1acdae. Otherwise reviewers will suspect a misconfigured
    baseline.
- **BabelRTS** (language-agnostic, file-level, regex-based): unsafe on Python (76.6% SafeR in NameRTS's study).
- **pytest-rts** (F-Secure/WithSecure): coverage-context RTS for pytest; granularity and fixture handling undocumented.
- **Kauhanen et al.** (SANER 2021 workshop VST): coverage-based Python RTS tool. File-level missed 0–2% of mutants;
  line-level missed 16–24%. Shows that finer granularity costs safety in Python.
- **pytest-testmon**: coverage.py-based; does not track static files or external services; documentation silent on
  module-level code and fixtures.
- **NodeSRT** (ICSE 2021 SRC): selective regression testing for Node.js.
- **Python import as an execution boundary** (Chen & Li, 2026, arXiv 2609.14791): 1,429 import-related bugs;
  module-level code and package initialization activate 98.3%; static analysers miss initialization-order changes.
  **Good motivation citation for channel A** (import-time code matters and tools are blind to it).

### 2.3 Shared state, pollution, dependent tests (background for channels A and C)
- **PolDet** (Gyori, Shi, Hariri, Marinov, ISSTA 2015): serializes the heap reachable from static fields before and after
  each test and diffs it. **The closest technique to our value snapshot**, but for detecting polluting tests, not selection.
  Must be cited and contrasted.
- **VMVM / unit test virtualization** (Bell & Kaiser, ICSE 2014): isolates static state between tests cheaply.
- **ElectricTest** (Bell et al., ESEC/FSE 2015): detects data dependencies between tests via static fields.
- **Test independence assumption** (Zhang et al., ISSTA 2014); **dependent-test-aware regression testing** (Lam et al.,
  ISSTA 2020): dependence-unaware RTS produces flaky failures in 90% of suites with dependent tests.
- **Maven test isolation performance** (Nie et al., ISSTA 2020): the cost of process-level isolation.

### 2.4 Coding agents and tests
- **TDAD** (Alonso, Yovine, Braberman, arXiv 2603.17973, 2026): the most direct agent-RTS competitor.
  - Static AST graph; weighted strategies; cap of 50 tests; exposed to the agent as a grep-able test map plus a SKILL.md.
  - SWE-bench Verified with Qwen3-Coder 30B: test-level regressions 6.08% → 1.82%, resolution 31% → 29%.
  - Small samples, local models only.
  - In our runs it misses on almost every change and does not finish on sympy.
- **TestPrune** ("Can Old Tests Do New Tricks", arXiv 2510.18270, 2025): issue-based test-suite minimization *before* a
  patch exists (LLM predicts suspicious functions, then greedy coverage). 27× faster than the full suite; +8–13%
  resolution across agents. A different problem from post-edit RTS, but the closest positive evidence that cheaper
  regression tests help agents.
- **To Run or Not to Run** (Lin et al., ISSTA 2026, arXiv 2606.26978):
  - Agents average 8.8 test runs per task.
  - Banning execution cuts tokens by 56–62% with about 1 pp lower resolution (not significant).
  - Recommends adaptive, cost-aware execution.
  - **Reviewers will raise this.** Our answer: execution is expensive and its value comes from the right tests, which is
    exactly the case for safe, cheap selection. Regressions (P2P failures) are the outcome that execution protects.
- **Cost-inefficient behaviors in coding agents** (arXiv 2609.30725): test re-execution is one of three wasteful
  behaviors; together they account for up to 22.75% of task cost.
- **Rethinking agent-generated tests** (arXiv 2602.07900): agent-written tests are weakly tied to success; existing human
  tests are the primary validation source.
- **Coding Agents Don't Know When to Act** (FixedBench, arXiv 2605.07769): 35–65% unnecessary edits.
- **RETRACE** (arXiv 2608.08950): LLM-based patch-issue alignment verifier; +3.6–7.0% Pass@1.

### 2.5 Behavioural differencing (background for any "impact checking" follow-up)
- **BERT / behavioural regression testing** (Jin, Orso, Xie, ~2010): generates tests and compares behaviour between
  versions. Differential, not selection.

## 3. What reviewers will raise, and our answers

1. *"NameRTS already handles import-time code, fixtures and isolation."* Answer: it handles import-time code coarsely
   (shared key, so all tests) and fixtures statically. Proviso compares values, so it selects only the readers of
   changed state. Show the numbers: how often import-time changes force NameRTS to select everything, versus Proviso.
2. *"Your NameRTS numbers contradict its paper."* Answer: different ground truth (failing tests vs affected tests), plus
   data-file tests and the setup details. We need a side-by-side explanation, ideally re-scored on its own metric too.
3. *"Execution doesn't help agents much (To Run or Not to Run)."* Answer: that makes cost the bottleneck, so cheap, safe
   selection is what makes execution worth keeping. An agent study is needed to show this directly.
4. *"PolDet already diffs state."* Answer: different goal (detecting pollution per test) and different trigger;
   Proviso diffs state across versions to select tests.
5. *"Only 5 repos."* Answer: scale up to 10+; NameRTS used 10.

## 4. Still to check (not covered by this pass)

- Full texts behind paywalls: the Ekstazi details on static initializers; the HyRTS hybrid RTS paper; the Yoo & Harman
  survey sections on dynamic languages.
- A Google Scholar sweep for "Python" + "regression test selection" in 2024–2026 venues (ICST, ASE, SANER, MSR), and
  for "import-time" + "test".
- Industrial tools: Datadog Intelligent Test Runner, Launchable, Bazel/Pants; how they treat module-level code.
- Whether pytest-cov's "test" context attributes fixture setup to tests (decides how novel channel B is versus
  testmon/pytest-rts).
- Any 2026 agent-RTS work beyond TDAD (re-check arXiv monthly until submission).

## 5. Sources
- NameRTS: https://arxiv.org/abs/2605.25356 (accepted at ISSTA 2026; ACM DL: https://dl.acm.org/doi/abs/10.1145/3832218)
- Kauhanen et al., Python RTS tool (SANER 2021 workshop): https://researchportal.helsinki.fi/en/publications/regression-test-selection-tool-for-python-in-continuous-integrati/
- pytest-rts: https://github.com/F-Secure/pytest-rts
- testmon: https://www.testmon.org/
- STARTS: https://www.cs.cornell.edu/~legunsen/pubs/LegunsenETAL17STARTS.pdf
- Static RTS study (FSE 2016): https://mir.cs.illinois.edu/farah/publications/fse16_static.pdf
- Reflection-aware static RTS: https://lingming.cs.illinois.edu/publications/oopsla2019.pdf
- RTSCheck: https://www.cs.cornell.edu/~legunsen/pubs/ZhuETAL19RTSCheck.pdf
- More precise RTS (ISSTA 2023): https://par.nsf.gov/servlets/purl/10421200
- uRTS (ICSE 2023): https://conf.researchr.org/details/icse-2023/icse-2023-technical-track/59/Test-Selection-for-Unified-Regression-Testing
- Ekstazi: https://github.com/gliga/ekstazi
- Predictive Test Selection: https://ar5iv.arxiv.org/html/1810.05286
- PolDet (ISSTA 2015): https://mir.cs.illinois.edu/gyori/pubs/issta15pollution.pdf
- Dependent-test-aware regression testing (ISSTA 2020): https://homes.cs.washington.edu/~mernst/pubs/dependent-tests-issta2020-abstract.html
- Test independence (ISSTA 2014): https://cs.gmu.edu/~winglam/publications/2014/test-independence-issta2014.pdf
- VMVM: https://academiccommons.columbia.edu/doi/10.7916/D89C6VF2
- Python import as an execution boundary: https://arxiv.org/pdf/2609.14791
- NodeSRT: https://arxiv.org/pdf/2104.00142
- Side-effect-based RTS (NEXTA 2024): https://conf.researchr.org/details/icst-2024/nexta-2024-papers/3/Selecting-good-regression-tests-based-on-a-classification-of-side-effects
- TDAD: https://arxiv.org/abs/2603.17973
- TestPrune: https://arxiv.org/pdf/2510.18270
- To Run or Not to Run (ISSTA 2026): https://arxiv.org/html/2606.26978
- Cost-inefficient behaviors: https://www.alphaxiv.org/abs/2609.30725
- Agent-generated tests: https://arxiv.org/html/2602.07900v2
- FixedBench: https://arxiv.org/html/2605.07769v1
- RETRACE: https://arxiv.org/abs/2608.08950
- BERT: https://sites.cc.gatech.edu/grads/w/wjin6/mypage/bert.html
