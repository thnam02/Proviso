# SQLAlchemy (10f4d1e2d; targets test/base test/sql)

## Planted bugs: 95 changes, 58 break tests (10682 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 58 | 0 | 100.0% (100.0%) |
| name_match | 54 of 58 | 10434 | 0.5% (0.0%) |
| static_imports | 0 of 58 | 0 | 100.0% (100.0%) |
| file_coverage | 5 of 58 | 59 | 41.7% (23.7%) |
| testmon | 7 of 58 | 1207 | 29.9% (14.0%) |
| func_only | 35 of 58 | 5684 | 28.7% (0.0%) |
| func_file | 9 of 58 | 1836 | 75.5% (77.3%) |
| proviso | 9 of 58 | 1716 | 79.1% (80.0%) |
| namerts | 28 of 58 | 3505 | 31.0% (5.0%) |

End to end (plain s): full suite median 23.5; Proviso (selection + selected tests) median 20.5, mean 19.9; faster on 90 of 95; selection median 1.65 s

## Real commits: 20 changes, 11 break tests (52 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 11 | 0 | 100.0% (100.0%) |
| name_match | 9 of 11 | 49 | 1.3% (0.3%) |
| static_imports | 0 of 11 | 0 | 100.0% (100.0%) |
| file_coverage | 2 of 11 | 2 | 70.8% (86.8%) |
| testmon | 2 of 11 | 2 | 49.2% (39.0%) |
| func_only | 4 of 11 | 28 | 59.4% (67.6%) |
| func_file | 3 of 11 | 27 | 72.6% (80.4%) |
| proviso | 2 of 11 | 2 | 80.3% (84.4%) |
| namerts | 3 of 11 | 8 | 41.2% (30.1%) |

End to end (plain s): full suite median 26.0; Proviso (selection + selected tests) median 24.2, mean 21.5; faster on 16 of 20; selection median 1.98 s
