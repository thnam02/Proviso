# pygments (156d85fdd1; targets tests)

## Planted bugs: 94 changes, 56 break tests (700 failing tests); 14 flaky failures dropped (passed when re-run)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 56 | 0 | 100.0% (100.0%) |
| name_match | 56 of 56 | 699 | 0.0% (0.0%) |
| static_imports | 18 of 56 | 356 | 79.1% (68.3%) |
| file_coverage | 56 of 56 | 700 | 0.0% (0.0%) |
| testmon | 0 of 56 | 0 | 100.0% (100.0%) |
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
| file_coverage | 28 of 29 | 56 | 0.8% (0.0%) |
| testmon | 1 of 29 | 2 | 100.0% (100.0%) |
| func_only | 24 of 29 | 50 | 1.4% (0.0%) |
| func_file | 1 of 29 | 12 | 9.7% (4.2%) |
| proviso | 1 of 29 | 3 | 19.5% (3.1%) |
| namerts | 29 of 29 | 57 | 2.2% (0.0%) |
| tdad | 29 of 29 | 57 | 1.5% (0.4%) |
| tdad_nocap | 29 of 29 | 57 | 2.2% (0.4%) |

End to end (plain s): full suite median 9.5; Proviso median 1.5, mean 2.9; faster on 46 of 54; selection median 1.23 s
