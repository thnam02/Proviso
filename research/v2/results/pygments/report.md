# pygments (156d85fdd1; targets tests)

## Planted bugs: 94 changes, 56 break tests (710 failing tests); 4 flaky failures dropped (passed when re-run)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 56 | 0 | 100.0% (100.0%) |
| name_match | 56 of 56 | 709 | 0.0% (0.0%) |
| static_imports | 18 of 56 | 356 | 79.1% (68.3%) |
| file_coverage | 25 of 56 | 149 | 11.5% (3.9%) |
| testmon | 26 of 56 | 421 | 7.0% (3.8%) |
| func_only | 31 of 56 | 411 | 2.1% (0.0%) |
| func_file | 22 of 56 | 390 | 6.0% (1.6%) |
| proviso | 0 of 56 | 0 | 28.4% (2.8%) |
| namerts | 56 of 56 | 588 | 4.8% (0.0%) |
| tdad | 56 of 56 | 629 | 2.3% (0.1%) |
| tdad_nocap | 56 of 56 | 627 | 4.8% (0.1%) |

End to end (plain s): full suite median 7.9; Proviso median 1.1, mean 2.9; faster on 72 of 94; selection median 0.96 s

(2 failing tests left out: they were created by the change, so no selector could pick them)

## Real commits: 54 changes, 29 break tests (55 failing tests); 5 flaky failures dropped (passed when re-run)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 29 | 0 | 100.0% (100.0%) |
| name_match | 29 of 29 | 55 | 0.0% (0.0%) |
| static_imports | 3 of 29 | 5 | 65.2% (66.8%) |
| file_coverage | 15 of 29 | 32 | 7.0% (5.1%) |
| testmon | 15 of 29 | 32 | 17.3% (5.3%) |
| func_only | 24 of 29 | 48 | 1.4% (0.0%) |
| func_file | 1 of 29 | 10 | 9.7% (4.2%) |
| proviso | 1 of 29 | 1 | 19.5% (3.1%) |
| namerts | 29 of 29 | 55 | 2.2% (0.0%) |
| tdad | 29 of 29 | 55 | 1.5% (0.4%) |
| tdad_nocap | 29 of 29 | 55 | 2.2% (0.4%) |

End to end (plain s): full suite median 9.5; Proviso median 1.5, mean 2.9; faster on 46 of 54; selection median 1.23 s

testmon: run without the test files that have no extension (pytest-testmon crashes on them); their tests count as always selected by testmon and file_coverage
