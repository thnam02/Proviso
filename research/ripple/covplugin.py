"""pytest plugin: record, per test, which package functions it calls (file, first line) and its duration.
Enable with: python -m pytest -p covplugin ... (this file's folder on PYTHONPATH); output path in COVMAP_OUT."""

import json
import os
import sys
import time

PKG = os.path.join(os.getcwd(), "sqlglot") + os.sep
_cur: set = set()
_map: dict = {}


def _prof(frame, event, arg):
    if event == "call":
        fn = frame.f_code.co_filename
        if fn.startswith(PKG):
            _cur.add((fn[len(PKG) - len("sqlglot/"):], frame.f_code.co_firstlineno))


def pytest_runtest_call(item):
    _cur.clear()
    sys.setprofile(_prof)


def pytest_runtest_teardown(item, nextitem):
    sys.setprofile(None)


def pytest_runtest_logreport(report):
    if report.when == "call":
        _map[report.nodeid] = {"funcs": sorted(_cur), "time": round(report.duration, 4), "ok": report.passed}


def pytest_sessionfinish(session, exitstatus):
    json.dump(_map, open(os.environ["COVMAP_OUT"], "w"))
