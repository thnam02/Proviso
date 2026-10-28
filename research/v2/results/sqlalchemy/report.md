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
