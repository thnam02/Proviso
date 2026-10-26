# sqlglot (7f1cf60c88; targets tests)

## Planted bugs: 95 changes, 59 break tests (778 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 59 | 0 | 100.0% (100.0%) |
| name_match | 41 of 59 | 713 | 11.9% (0.6%) |
| static_imports | 13 of 59 | 16 | 63.5% (100.0%) |
| file_coverage | 13 of 59 | 94 | 30.8% (6.1%) |
| testmon | 5 of 59 | 170 | 99.1% (100.0%) |
| func_only | 37 of 59 | 245 | 4.7% (0.0%) |
| func_file | 14 of 59 | 93 | 16.9% (5.2%) |
| proviso | 0 of 59 | 0 | 24.1% (4.5%) |
| namerts | 25 of 59 | 91 | 50.9% (20.7%) |
| tdad | 56 of 59 | 743 | 1.1% (0.8%) |
| tdad_nocap | 45 of 59 | 418 | 47.3% (84.4%) |

End to end (plain s): full suite median 27.4; Proviso median 2.1, mean 7.2; faster on 80 of 95; selection median 0.86 s

## Real commits: 52 changes, 32 break tests (45 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 32 | 0 | 100.0% (100.0%) |
| name_match | 13 of 32 | 18 | 14.6% (0.9%) |
| static_imports | 9 of 32 | 13 | 59.3% (100.0%) |
| file_coverage | 2 of 32 | 2 | 32.2% (5.9%) |
| testmon | 0 of 32 | 0 | 100.0% (100.0%) |
| func_only | 9 of 32 | 10 | 13.5% (1.2%) |
| func_file | 1 of 32 | 1 | 23.6% (6.1%) |
| proviso | 0 of 32 | 0 | 32.4% (7.8%) |
| namerts | 14 of 32 | 19 | 46.7% (20.3%) |
| tdad | 29 of 32 | 39 | 0.9% (0.3%) |
| tdad_nocap | 19 of 32 | 24 | 37.6% (2.9%) |

End to end (plain s): full suite median 31.2; Proviso median 4.0, mean 11.1; faster on 43 of 52; selection median 1.10 s

# sympy (01c75e920f; targets sympy/functions)

# sqlalchemy (10f4d1e2d7; targets test/base test/sql)

## Planted bugs: 94 changes, 61 break tests (8250 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 61 | 0 | 100.0% (100.0%) |
| name_match | 54 of 61 | 8066 | 0.7% (0.0%) |
| static_imports | 0 of 61 | 0 | 100.0% (100.0%) |
| file_coverage | 3 of 61 | 35 | 43.5% (23.3%) |
| testmon | 6 of 61 | 1146 | 25.9% (13.1%) |
| func_only | 36 of 61 | 4091 | 28.3% (0.0%) |
| func_file | 4 of 61 | 22 | 80.7% (78.8%) |
| proviso | 3 of 61 | 14 | 87.2% (100.0%) |
| namerts | 26 of 61 | 2875 | 29.5% (3.1%) |
| tdad | 61 of 61 | 8241 | 0.2% (0.0%) |
| tdad_nocap | 34 of 61 | 5439 | 83.7% (87.1%) |

End to end (plain s): full suite median 24.2; Proviso median 26.1, mean 22.5; faster on 38 of 94; selection median 1.88 s

## Real commits: 22 changes, 10 break tests (27 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 10 | 0 | 100.0% (100.0%) |
| name_match | 8 of 10 | 24 | 1.1% (0.2%) |
| static_imports | 0 of 10 | 0 | 100.0% (100.0%) |
| file_coverage | 2 of 10 | 2 | 68.0% (87.2%) |
| testmon | 2 of 10 | 2 | 39.2% (21.8%) |
| func_only | 3 of 10 | 3 | 62.1% (69.5%) |
| func_file | 1 of 10 | 1 | 86.2% (94.7%) |
| proviso | 0 of 10 | 0 | 92.3% (100.0%) |
| namerts | 3 of 10 | 8 | 36.8% (6.7%) |
| tdad | 10 of 10 | 27 | 0.1% (0.0%) |
| tdad_nocap | 3 of 10 | 6 | 74.4% (84.6%) |

End to end (plain s): full suite median 24.5; Proviso median 25.9, mean 22.4; faster on 4 of 22; selection median 1.88 s

# pygments (156d85fdd1; targets tests)

## Planted bugs: 94 changes, 56 break tests (714 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 44 of 56 | 204 | 100.0% (100.0%) |
| name_match | 56 of 56 | 713 | 0.0% (0.0%) |
| static_imports | 55 of 56 | 561 | 34.0% (0.0%) |
| file_coverage | 56 of 56 | 714 | 0.0% (0.0%) |
| testmon | 44 of 56 | 204 | 100.0% (100.0%) |
| func_only | 47 of 56 | 534 | 3.8% (0.0%) |
| func_file | 46 of 56 | 528 | 9.5% (4.5%) |
| proviso | 44 of 56 | 205 | 30.9% (7.6%) |
| namerts | 56 of 56 | 590 | 15.2% (0.0%) |
| tdad | 56 of 56 | 628 | 7.1% (0.3%) |
| tdad_nocap | 56 of 56 | 626 | 15.2% (0.3%) |

End to end (plain s): full suite median 2.5; Proviso median 1.1, mean 1.5; faster on 70 of 94; selection median 1.00 s

## Real commits: 53 changes, 34 break tests (62 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 27 of 34 | 52 | 100.0% (100.0%) |
| name_match | 34 of 34 | 62 | 0.1% (0.0%) |
| static_imports | 32 of 34 | 60 | 12.9% (0.0%) |
| file_coverage | 33 of 34 | 61 | 0.9% (0.0%) |
| testmon | 27 of 34 | 52 | 89.5% (100.0%) |
| func_only | 31 of 34 | 59 | 1.7% (0.0%) |
| func_file | 31 of 34 | 59 | 12.9% (8.2%) |
| proviso | 30 of 34 | 56 | 24.1% (7.4%) |
| namerts | 34 of 34 | 62 | 3.8% (0.0%) |
| tdad | 34 of 34 | 62 | 4.3% (1.0%) |
| tdad_nocap | 34 of 34 | 62 | 6.4% (1.0%) |

End to end (plain s): full suite median 3.1; Proviso median 1.3, mean 1.9; faster on 44 of 53; selection median 1.07 s

# datasette (a8e13cc489; targets tests)

