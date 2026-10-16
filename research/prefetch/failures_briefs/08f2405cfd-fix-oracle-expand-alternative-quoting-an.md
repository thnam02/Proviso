Tests that already fail at this commit, before any change (not caused by you):
- tests.test_expressions.TestExprs.test_convert — error inside the test
- tests.dialects.test_bigquery — test module fails to import
- tests.test_executor — test module fails to import
- tests.test_optimizer — test module fails to import
- Cause: pytz is not installed in this environment. All 4 errors exist before any change and are not caused by your work.
