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
