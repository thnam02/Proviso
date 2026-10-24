# SQLAlchemy (10f4d1e2d; targets test/base test/sql)

## Planted bugs: 3 changes, 1 break tests (3 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 1 | 0 | 100.0% (100.0%) |
| name_match | 1 of 1 | 3 | 0.4% (0.0%) |
| static_imports | 0 of 1 | 0 | 100.0% (100.0%) |
| file_coverage | 0 of 1 | 0 | 41.7% (22.6%) |
| testmon | 0 of 1 | 0 | 41.5% (22.6%) |
| func_only | 1 of 1 | 3 | 23.8% (0.0%) |
| func_file | 0 of 1 | 0 | 80.9% (85.0%) |
| proviso | 0 of 1 | 0 | 80.8% (80.5%) |
| namerts | 1 of 1 | 3 | 0.0% (0.0%) |

End to end (plain s): full suite median 46.7; Proviso (selection + selected tests) median 40.9, mean 41.0; faster on 3 of 3; selection median 3.35 s

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
| namerts | 1 of 1 | 1 | 0.0% (0.0%) |

End to end (plain s): full suite median 51.6; Proviso (selection + selected tests) median 43.9, mean 42.6; faster on 3 of 3; selection median 2.94 s
