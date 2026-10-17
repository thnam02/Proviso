"""pytest plugin: per-test coverage map for impact selection. Enable with -p covplugin; output path in COVMAP_OUT.

Per test:  funcs    package functions it calls (file, first line)
           classes  package classes whose methods ran on an instance of them or of a subclass ("file:Qualname"),
                    including every package class in the instance type's MRO (a subclass's table is read through
                    inherited methods)
           always   the test started a subprocess (its coverage cannot be observed), so it always runs
           time, ok
"__global__": functions that ran outside any test (imports, collection, class bodies): editing one affects tests
              without them recording it, so it forces the full suite.
"""

import json
import os
import sys

ROOT = os.getcwd()
PKG = os.path.join(ROOT, os.environ.get("COVMAP_PKG", "sqlglot")) + os.sep
_cur: set = set()
_cls: set = set()
_glob: set = set()
_always = [False]
_in_test = [False]
_map: dict = {}
_mro_cache: dict = {}


def _classes_of(tp):
    k = tp  # keyed by the type itself: ids of freed dynamic classes are reused
    try:
        got = _mro_cache.get(k)
    except TypeError:
        return []
    if got is None:
        got = []
        for c in getattr(tp, "__mro__", ()):
            mod = sys.modules.get(getattr(c, "__module__", ""), None)
            fn = getattr(mod, "__file__", None) or ""
            if fn.startswith(PKG):
                got.append(f"{os.path.relpath(fn, ROOT)}:{c.__qualname__}")
        _mro_cache[k] = got
    return got


def _prof(frame, event, arg):
    if event != "call":
        return
    code = frame.f_code
    fn = code.co_filename
    if fn.startswith(PKG):
        key = (fn[len(ROOT) + 1:], code.co_firstlineno)
        if not _in_test[0]:
            _glob.add(key)
            return
        _cur.add(key)
        if code.co_argcount and code.co_varnames[0] in ("self", "cls"):
            obj = frame.f_locals.get(code.co_varnames[0])
            if obj is not None:
                for c in _classes_of(obj if isinstance(obj, type) else type(obj)):
                    _cls.add(c)
    elif _in_test[0] and code.co_name == "__init__" and fn.endswith(os.path.join("subprocess.py")):
        _always[0] = True


def pytest_sessionstart(session):
    import threading
    sys.setprofile(_prof)
    threading.setprofile(_prof)  # code run in threads (e.g. concurrent import tests) is attributed too


def pytest_runtest_call(item):
    _cur.clear()
    _cls.clear()
    _always[0] = False
    _in_test[0] = True


def pytest_runtest_teardown(item, nextitem):
    _in_test[0] = False


def pytest_runtest_logreport(report):
    if report.when == "call":
        _map[report.nodeid] = {"funcs": sorted(_cur), "classes": sorted(_cls), "always": _always[0],
                               "time": round(report.duration, 4), "ok": report.passed}


def pytest_sessionfinish(session, exitstatus):
    sys.setprofile(None)
    _map["__global__"] = {"funcs": sorted(_glob)}
    json.dump(_map, open(os.environ["COVMAP_OUT"], "w"))
