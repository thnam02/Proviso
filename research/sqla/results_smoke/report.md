# SQLAlchemy (10f4d1e2d; targets test/base test/sql)

## Planted bugs: 6 changes, 3 break tests (643 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 3 | 0 | 100.0% (100.0%) |
| name_match | 3 of 3 | 643 | 0.4% (0.0%) |
| static_imports | 0 of 3 | 0 | 100.0% (100.0%) |
| file_coverage | 0 of 3 | 0 | 41.5% (22.6%) |
| testmon | 0 of 3 | 0 | 26.8% (18.3%) |
| func_only | 2 of 3 | 598 | 22.8% (0.0%) |
| func_file | 0 of 3 | 0 | 78.2% (80.3%) |
| proviso | 0 of 3 | 0 | 78.7% (80.5%) |
| namerts | 2 of 3 | 8 | 13.7% (0.0%) |

End to end (plain s): full suite median 46.7; Proviso (selection + selected tests) median 41.0, mean 39.5; faster on 6 of 6; selection median 3.17 s

## Real commits: 3 changes, 1 break tests (1 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 1 | 0 | 100.0% (100.0%) |
| name_match | 1 of 1 | 1 | 0.4% (0.0%) |
| static_imports | 0 of 1 | 0 | 100.0% (100.0%) |
| file_coverage | 0 of 1 | 0 | 45.0% (22.5%) |
| testmon | 0 of 1 | 0 | 9.4% (12.5%) |
| func_only | 0 of 1 | 0 | 73.4% (75.4%) |
| func_file | 0 of 1 | 0 | 74.0% (75.4%) |
| proviso | 0 of 1 | 0 | 78.6% (82.8%) |
| namerts | 1 of 1 | 1 | 0.3% (0.0%) |

End to end (plain s): full suite median 51.6; Proviso (selection + selected tests) median 44.1, mean 43.0; faster on 3 of 3; selection median 3.43 s
