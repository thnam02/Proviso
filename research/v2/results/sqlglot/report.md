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

End to end (plain s): full suite median 31.2; Proviso median 4.0, mean 11.1; faster on 43 of 52; selection median 1.10 s
