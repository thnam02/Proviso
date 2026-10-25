"""sympy's pytest config selects tests with `-m 'not slow and not tooslow'`, and pytest-testmon turns its selection
off whenever -m is used. This plugin drops the same tests (marked slow or tooslow) at collection instead, so the test
set is unchanged and testmon's selection stays active (run with -o addopts= -p noslow)."""


def pytest_collection_modifyitems(config, items):
    keep, drop = [], []
    for it in items:
        (drop if it.get_closest_marker("slow") or it.get_closest_marker("tooslow") else keep).append(it)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep
