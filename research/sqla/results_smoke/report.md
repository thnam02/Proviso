# SQLAlchemy (10f4d1e2d; targets test/base test/sql)

## Planted bugs: 6 changes, 3 break tests (643 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 3 | 0 | 100.0% (100.0%) |
| name_match | 3 of 3 | 643 | 0.4% (0.0%) |
| static_imports | 0 of 3 | 0 | 100.0% (100.0%) |
| file_coverage | 0 of 3 | 0 | 41.5% (22.6%) |
| testmon | 3 of 3 | 643 | 0.0% (0.0%) |
| func_only | 2 of 3 | 598 | 22.8% (0.0%) |
| func_file | 0 of 3 | 0 | 78.2% (80.3%) |
| proviso | 1 of 3 | 3 | 78.7% (80.5%) |
| namerts | 3 of 3 | 643 | 0.0% (0.0%) |

End to end (plain s): full suite median 46.7; Proviso (selection + selected tests) median 40.9, mean 39.6; faster on 6 of 6; selection median 3.24 s
