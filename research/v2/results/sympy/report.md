# sympy (01c75e920f; targets sympy/functions)

(4 planted bugs left out: the test suite hung past the timeout on them)

## Planted bugs: 91 changes, 47 break tests (5303 failing tests); 2 flaky failures dropped (passed when re-run)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 47 | 0 | 100.0% (100.0%) |
| name_match | 36 of 47 | 5272 | 2.1% (0.0%) |
| static_imports | 0 of 47 | 0 | 100.0% (100.0%) |
| file_coverage | 13 of 47 | 196 | 58.2% (79.5%) |
| testmon | 6 of 39 | 85 | 31.6% (4.0%) |
| func_only | 26 of 47 | 4749 | 10.0% (0.0%) |
| func_file | 13 of 47 | 630 | 38.3% (10.3%) |
| proviso | 3 of 47 | 3 | 56.5% (77.5%) |
| namerts | 7 of 47 | 837 | 66.1% (98.5%) |

testmon: could not run on 8 change(s) (e.g. the change breaks collection under it); those changes are left out of its row

End to end (plain s): full suite median 58.0; Proviso median 47.0, mean 36.1; faster on 56 of 91; selection median 2.26 s

## Real commits: 21 changes, 1 break tests (2 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 1 | 0 | 100.0% (100.0%) |
| name_match | 0 of 1 | 0 | 3.4% (0.0%) |
| static_imports | 0 of 1 | 0 | 100.0% (100.0%) |
| file_coverage | 0 of 1 | 0 | 87.4% (97.7%) |
| testmon | 0 of 1 | 0 | 55.7% (79.0%) |
| func_only | 0 of 1 | 0 | 41.1% (9.8%) |
| func_file | 0 of 1 | 0 | 56.6% (83.1%) |
| proviso | 0 of 1 | 0 | 44.0% (9.8%) |
| namerts | 0 of 1 | 0 | 57.2% (94.2%) |

End to end (plain s): full suite median 60.5; Proviso median 5.3, mean 27.7; faster on 14 of 21; selection median 0.11 s

TDAD: did not complete: TDAD's test linking ran out of memory (over 23 GB)
