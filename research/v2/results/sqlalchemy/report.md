# sqlalchemy (10f4d1e2d7; targets test/base test/sql)

## Planted bugs: 94 changes, 28 break tests (117 failing tests); 8133 flaky failures dropped (passed when re-run)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 28 | 0 | 100.0% (100.0%) |
| name_match | 21 of 28 | 71 | 0.7% (0.0%) |
| static_imports | 0 of 28 | 0 | 100.0% (100.0%) |
| file_coverage | 0 of 28 | 0 | 43.5% (23.3%) |
| testmon | 0 of 28 | 0 | 25.9% (13.1%) |
| func_only | 15 of 28 | 64 | 28.3% (0.0%) |
| func_file | 0 of 28 | 0 | 80.7% (78.8%) |
| proviso | 0 of 28 | 0 | 87.2% (100.0%) |
| namerts | 8 of 28 | 34 | 29.5% (3.1%) |
| tdad | 28 of 28 | 116 | 0.2% (0.0%) |
| tdad_nocap | 1 of 28 | 1 | 83.7% (87.1%) |

End to end (plain s): full suite median 24.2; Proviso median 26.1, mean 22.5; faster on 38 of 94; selection median 1.88 s

## Real commits: 22 changes, 8 break tests (20 failing tests); 7 flaky failures dropped (passed when re-run)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 8 | 0 | 100.0% (100.0%) |
| name_match | 6 of 8 | 18 | 1.1% (0.2%) |
| static_imports | 0 of 8 | 0 | 100.0% (100.0%) |
| file_coverage | 2 of 8 | 2 | 68.0% (87.2%) |
| testmon | 2 of 8 | 2 | 39.2% (21.8%) |
| func_only | 3 of 8 | 3 | 62.1% (69.5%) |
| func_file | 1 of 8 | 1 | 86.2% (94.7%) |
| proviso | 0 of 8 | 0 | 92.3% (100.0%) |
| namerts | 2 of 8 | 2 | 36.8% (6.7%) |
| tdad | 8 of 8 | 20 | 0.1% (0.0%) |
| tdad_nocap | 1 of 8 | 4 | 74.4% (84.6%) |

End to end (plain s): full suite median 24.5; Proviso median 25.9, mean 22.4; faster on 4 of 22; selection median 1.88 s
