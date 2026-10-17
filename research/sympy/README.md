# Change-impact selection on sympy

Tasks: 13 fixes merged into sympy in 2025-26, in its slowest subpackages (eval/tasks_sympy; build.py, verify.py,
prompts.py). Test time on this machine: integrals 195 s, solvers 159 s, functions 104 s, series 94 s, polys 73 s,
matrices 62 s, simplify 40 s, core 39 s; the default suite about 25 minutes.

Coverage maps (assets.py): the task's subpackages plus sympy/core at the base commit, with sympy's cache cleared before
every test, so a test records what it depends on even when an earlier test computed (and cached) it.

## Planted bugs (mutants_sympy.py, seed 7)

30 bugs in sympy/functions and sympy/core; ground truth = sympy/functions tests (581) run normally on the bugged tree.

| kind | planted | caught by the suite | selected every failing test | median tests selected |
|---|---|---|---|---|
| function (comparison/boolean flip) | 10 | 4 (+1 suite timeout, full selection) | 4/4 | 1 of 581 |
| class (table entry / boolean attribute) | 10 | 9 | 9/9 | 581 |
| module (table entry / boolean) | 10 | 4 | 4/4 | 581 |

Every caught bug was selected (17/17). Class- and module-level sites in sympy are almost all assumption flags
(`is_integer = True`) and assumption tables, which the assumption system reads from everywhere, so selecting the whole
suite is the right answer for them.

## Live study: plain agent vs Proviso (Claude Code, claude-sonnet-5-5, 13 tasks x 2 reps per arm)

Both arms ran side by side on a 2-core machine (5 Proviso runs at the end ran alone; excluding them changes nothing).
Test time = time inside the agent's test commands, from transcript timestamps (analyse.py).

| per run | plain | Proviso |
|---|---|---|
| resolved (hidden tests) | 25/26 | 23/26 (the 3 failures: 2 on the hardest task, which plain also failed once; 1 run Proviso never intercepted) |
| existing tests broken | 0 | 0 |
| time inside test commands, mean / median | 80 s / 67 s | 81 s / 40 s |
| tasks where Proviso's test time is lower | | 6 of 13 |
| cost, mean | $0.106 | $0.112 |

Proviso intercepted test runs in 18 of 26 runs and ran 64% of the tests in their scope, but the mean time spent
testing did not fall. Agents test narrowly on sympy: about 2 test commands per run, ~170-210 tests each (the
subpackages hold 300-2,500), chosen near the change. Those are mostly the affected tests already, and the affected tests
are the expensive ones; what selection removes from such a run is cheap.

## Offline: the same tasks with the real fix (offline_saving.py)

If the change is the reference fix and the whole subpackage is run, selection keeps 12% of the tests and 31% of the
test time (median task: 13% of the time); 5 of 13 tasks need under 5% of the time, 3 need over 90%.

Takeaway: the selection is safe and large when the agent runs a broad suite (here and on sqlglot, where agents run the
whole suite because it is fast: wall time -20% to -27%), but on a slow suite agents already narrow their test runs
themselves, so the live saving disappears.
