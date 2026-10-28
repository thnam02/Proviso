# datasette (a8e13cc489; targets tests)

## Planted bugs: 95 changes, 60 break tests (9502 failing tests); 1 flaky failures dropped (passed when re-run)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 60 | 0 | 100.0% (100.0%) |
| name_match | 56 of 60 | 9420 | 0.2% (0.0%) |
| static_imports | 6 of 60 | 334 | 89.1% (93.6%) |
| testmon | 3 of 58 | 48 | 92.5% (91.4%) |
| func_only | 29 of 60 | 6126 | 13.6% (0.0%) |
| func_file | 7 of 60 | 5438 | 32.9% (21.6%) |
| proviso | 2 of 60 | 194 | 71.6% (98.3%) |
| namerts | 11 of 60 | 6952 | 38.5% (23.5%) |
| tdad | 56 of 60 | 9215 | 1.9% (2.0%) |
| tdad_nocap | 24 of 60 | 1118 | 73.3% (83.9%) |

testmon: could not run on 2 change(s) (e.g. the change breaks collection under it); those changes are left out of its row

End to end (plain s): full suite median 63.2; Proviso median 63.2, mean 45.9; faster on 59 of 95; selection median 1.02 s

(1 failing tests left out: they were created by the change, so no selector could pick them)

## Real commits: 24 changes, 4 break tests (6 failing tests)

| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |
|---|---|---|---|
| retest_all | 0 of 4 | 0 | 100.0% (100.0%) |
| name_match | 3 of 4 | 3 | 0.4% (0.1%) |
| static_imports | 0 of 4 | 0 | 74.8% (92.4%) |
| testmon | 1 of 4 | 1 | 95.1% (94.5%) |
| func_only | 3 of 4 | 3 | 52.3% (41.7%) |
| func_file | 3 of 4 | 3 | 59.9% (65.3%) |
| proviso | 1 of 4 | 1 | 69.7% (98.5%) |
| namerts | 0 of 4 | 0 | 62.2% (71.7%) |
| tdad | 3 of 4 | 5 | 1.4% (1.1%) |
| tdad_nocap | 0 of 4 | 0 | 62.2% (79.3%) |

End to end (plain s): full suite median 64.3; Proviso median 53.2, mean 46.0; faster on 11 of 24; selection median 0.15 s

file_coverage: not reported here: testmon's per-test coverage records link project code to only about 250 of 2,939 tests on datasette, so file-level selection from them is not meaningful
