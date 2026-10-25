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

End to end (plain s): full suite median 3.1; Proviso median 1.3, mean 1.9; faster on 44 of 53; selection median 1.07 s
