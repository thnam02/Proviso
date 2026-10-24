"""pytest plugin: {node id: [passed, seconds]} for every test (call phase; a failing setup counts as a failure), and
{test file: [False, 0]} for a test module that fails to collect. Output path in OUTCOMES_OUT. No tracing."""
import json, os
_r = {}


def pytest_runtest_logreport(report):
    if report.when == "call":
        ok, t = _r.get(report.nodeid, [True, 0.0])
        _r[report.nodeid] = [ok and not report.failed, t + report.duration]
    elif report.failed:  # setup/teardown error
        _r[report.nodeid] = [False, _r.get(report.nodeid, [True, 0.0])[1] + report.duration]


def pytest_collectreport(report):
    if report.failed and report.nodeid.endswith(".py"):
        _r[report.nodeid] = [False, 0.0]


def pytest_sessionfinish(session, exitstatus):
    json.dump(_r, open(os.environ["OUTCOMES_OUT"], "w"))
