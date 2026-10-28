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

(4 planted bugs left out: the test suite hung past the timeout on them)

## Planted bugs: 91 changes, 47 break tests (5303 failing tests); 2 flaky failures dropped (passed when re-run)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 47 | 0 | 100.0% (100.0%) |
| name_match | 36 of 47 | 5272 | 2.1% (0.0%) |
| static_imports | 0 of 47 | 0 | 100.0% (100.0%) |
| file_coverage | 13 of 47 | 196 | 58.2% (79.5%) |
| testmon | 6 of 39 | 85 | 31.6% (4.0%) |
| func_only | 26 of 47 | 4749 | 10.0% (0.0%) |
| func_file | 13 of 47 | 630 | 38.3% (10.3%) |
| proviso | 3 of 47 | 3 | 56.5% (77.5%) |
| namerts | 7 of 47 | 837 | 66.1% (98.5%) |

testmon: could not run on 8 change(s) (e.g. the change breaks collection under it); those changes are left out of its row

End to end (plain s): full suite median 58.0; Proviso median 47.0, mean 36.1; faster on 56 of 91; selection median 2.26 s

## Real commits: 21 changes, 1 break tests (2 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 1 | 0 | 100.0% (100.0%) |
| name_match | 0 of 1 | 0 | 3.4% (0.0%) |
| static_imports | 0 of 1 | 0 | 100.0% (100.0%) |
| file_coverage | 0 of 1 | 0 | 87.4% (97.7%) |
| testmon | 0 of 1 | 0 | 55.7% (79.0%) |
| func_only | 0 of 1 | 0 | 41.1% (9.8%) |
| func_file | 0 of 1 | 0 | 56.6% (83.1%) |
| proviso | 0 of 1 | 0 | 44.0% (9.8%) |
| namerts | 0 of 1 | 0 | 57.2% (94.2%) |

End to end (plain s): full suite median 60.5; Proviso median 5.3, mean 27.7; faster on 14 of 21; selection median 0.11 s

TDAD: did not complete: TDAD's test linking ran out of memory (over 23 GB)

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

## Real commits: 30 changes, 10 break tests (27 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 10 | 0 | 100.0% (100.0%) |
| name_match | 8 of 10 | 24 | 0.9% (0.0%) |
| static_imports | 0 of 10 | 0 | 100.0% (100.0%) |
| file_coverage | 2 of 10 | 2 | 55.3% (53.5%) |
| testmon | 2 of 10 | 2 | 32.6% (17.8%) |
| func_only | 3 of 10 | 3 | 58.1% (68.1%) |
| func_file | 1 of 10 | 1 | 83.5% (86.1%) |
| proviso | 0 of 10 | 0 | 90.6% (100.0%) |
| namerts | 3 of 10 | 8 | 29.6% (0.1%) |
| tdad | 10 of 10 | 27 | 0.1% (0.0%) |
| tdad_nocap | 3 of 10 | 6 | 74.7% (84.6%) |

End to end (plain s): full suite median 24.5; Proviso median 25.9, mean 22.0; faster on 7 of 30; selection median 1.88 s

# pygments (156d85fdd1; targets tests)

## Planted bugs: 94 changes, 56 break tests (710 failing tests); 4 flaky failures dropped (passed when re-run)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 56 | 0 | 100.0% (100.0%) |
| name_match | 56 of 56 | 709 | 0.0% (0.0%) |
| static_imports | 18 of 56 | 356 | 79.1% (68.3%) |
| func_only | 31 of 56 | 411 | 2.1% (0.0%) |
| func_file | 22 of 56 | 390 | 6.0% (1.6%) |
| proviso | 0 of 56 | 0 | 28.4% (2.8%) |
| namerts | 56 of 56 | 588 | 4.8% (0.0%) |
| tdad | 56 of 56 | 629 | 2.3% (0.1%) |
| tdad_nocap | 56 of 56 | 627 | 4.8% (0.1%) |

End to end (plain s): full suite median 7.9; Proviso median 1.1, mean 2.9; faster on 72 of 94; selection median 0.96 s

## Real commits: 54 changes, 29 break tests (57 failing tests); 5 flaky failures dropped (passed when re-run)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 1 of 29 | 2 | 100.0% (100.0%) |
| name_match | 29 of 29 | 57 | 0.0% (0.0%) |
| static_imports | 3 of 29 | 7 | 65.2% (66.8%) |
| file_coverage | 0 of 1 | 0 | 7.6% (4.3%) |
| testmon | 0 of 1 | 0 | 100.0% (100.0%) |
| func_only | 24 of 29 | 50 | 1.4% (0.0%) |
| func_file | 1 of 29 | 12 | 9.7% (4.2%) |
| proviso | 1 of 29 | 3 | 19.5% (3.1%) |
| namerts | 29 of 29 | 57 | 2.2% (0.0%) |
| tdad | 29 of 29 | 57 | 1.5% (0.4%) |
| tdad_nocap | 29 of 29 | 57 | 2.2% (0.4%) |

End to end (plain s): full suite median 9.5; Proviso median 1.5, mean 2.9; faster on 46 of 54; selection median 1.23 s

# datasette (a8e13cc489; targets tests)

## Planted bugs: 95 changes, 60 break tests (9502 failing tests); 1 flaky failures dropped (passed when re-run)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 60 | 0 | 100.0% (100.0%) |
| name_match | 56 of 60 | 9420 | 0.2% (0.0%) |
| static_imports | 6 of 60 | 334 | 89.1% (93.6%) |
| file_coverage | 60 of 60 | 9037 | 3.3% (2.4%) |
| testmon | 3 of 58 | 48 | 92.5% (91.4%) |
| func_only | 29 of 60 | 6126 | 13.6% (0.0%) |
| func_file | 7 of 60 | 5438 | 32.9% (21.6%) |
| proviso | 2 of 60 | 194 | 71.6% (98.3%) |
| namerts | 11 of 60 | 6952 | 38.5% (23.5%) |
| tdad | 56 of 60 | 9215 | 1.9% (2.0%) |
| tdad_nocap | 24 of 60 | 1118 | 73.3% (83.9%) |

testmon: could not run on 2 change(s) (e.g. the change breaks collection under it); those changes are left out of its row

End to end (plain s): full suite median 63.2; Proviso median 63.2, mean 45.9; faster on 59 of 95; selection median 1.02 s

## Real commits: 24 changes, 4 break tests (7 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 1 of 4 | 1 | 100.0% (100.0%) |
| name_match | 3 of 4 | 4 | 0.4% (0.1%) |
| static_imports | 1 of 4 | 1 | 74.8% (92.4%) |
| file_coverage | 3 of 4 | 6 | 13.1% (7.5%) |
| testmon | 2 of 4 | 2 | 95.1% (94.5%) |
| func_only | 3 of 4 | 4 | 52.3% (41.7%) |
| func_file | 3 of 4 | 4 | 59.9% (65.3%) |
| proviso | 2 of 4 | 2 | 69.7% (98.5%) |
| namerts | 1 of 4 | 1 | 62.2% (71.7%) |
| tdad | 3 of 4 | 6 | 1.4% (1.1%) |
| tdad_nocap | 1 of 4 | 1 | 62.2% (79.3%) |

End to end (plain s): full suite median 64.3; Proviso median 53.2, mean 46.0; faster on 11 of 24; selection median 0.15 s

