"""pytest plugin: the same per-test coverage map as covplugin.py, recorded with sys.monitoring (PEP 669, Python 3.12+)
instead of sys.setprofile. Enable with -p covplugin_mon; output path in COVMAP_OUT.

Why it is faster: sys.setprofile calls back on every call, return and C call of every function; here only the start
of a Python function is reported, and a function that has already been recorded in the current test is switched off
(sys.monitoring.DISABLE) until the next test starts (sys.monitoring.restart_events). A function then costs one callback
per test instead of two per call. Methods (first argument self/cls) stay on, because the classes of the instances they
run on are recorded too (see covplugin.py), but only methods of the package are followed; everything outside the
package is switched off after its first call.

Output format and meaning: identical to covplugin.py.
"""

import json
import os
import sys

ROOT = os.getcwd()
PKG = os.path.join(ROOT, os.environ.get("COVMAP_PKG", "sqlglot")) + os.sep
SUBPROC = os.path.join("subprocess.py")
TOOL = 3  # a free sys.monitoring tool id (0-2 are reserved for debugger, coverage, profiler)
mon = sys.monitoring
DISABLE = mon.DISABLE

_cur: set = set()
_cls: set = set()
_glob: set = set()
_always = [False]
_in_test = [False]
_map: dict = {}
_mro_cache: dict = {}
# id(code) -> (code, kind); kind: None (not package code), "subprocess", or (key, is_method). Keyed by identity:
# code objects compare equal across files when their bodies match (co_filename is not compared), e.g. two empty
# __init__.py files. The code object is kept in the value so its id cannot be reused.
_kind: dict = {}


def _classes_of(tp):
    try:
        got = _mro_cache.get(tp)
    except TypeError:
        return []
    if got is None:
        got = []
        for c in getattr(tp, "__mro__", ()):
            mod = sys.modules.get(getattr(c, "__module__", ""), None)
            fn = getattr(mod, "__file__", None) or ""
            if fn.startswith(PKG):
                got.append(f"{os.path.relpath(fn, ROOT)}:{c.__qualname__}")
        _mro_cache[tp] = got
    return got


def _classify(code):
    fn = code.co_filename
    if fn.startswith(PKG):
        method = bool(code.co_argcount and code.co_varnames[0] in ("self", "cls"))
        k = ((fn[len(ROOT) + 1:], code.co_firstlineno), method)
    elif code.co_name == "__init__" and fn.endswith(SUBPROC):
        k = "subprocess"
    else:
        k = None
    _kind[id(code)] = (code, k)
    return k


def _start(code, offset):
    got = _kind.get(id(code))
    k = got[1] if got is not None else _classify(code)
    if k is None:
        return DISABLE  # not package code: never needed again (restart_events re-enables it per test; cheap)
    if k == "subprocess":
        if _in_test[0]:
            _always[0] = True
        return DISABLE
    key, method = k
    if not _in_test[0]:
        _glob.add(key)
        return DISABLE
    _cur.add(key)
    if not method:
        return DISABLE
    obj = sys._getframe(1).f_locals.get(code.co_varnames[0])
    if obj is not None:
        for c in _classes_of(obj if isinstance(obj, type) else type(obj)):
            _cls.add(c)
    return None


def pytest_sessionstart(session):
    mon.use_tool_id(TOOL, "proviso-cov")
    mon.register_callback(TOOL, mon.events.PY_START, _start)
    mon.set_events(TOOL, mon.events.PY_START)


_BEFORE = os.environ.get("COVMAP_BEFORE_TEST", "")


def _before_test():
    if not _BEFORE:
        return
    import importlib
    mod, fn = _BEFORE.split(":")
    getattr(importlib.import_module(mod), fn)()


def pytest_runtest_setup(item):
    _before_test()


def pytest_runtest_call(item):
    _cur.clear()
    _cls.clear()
    _always[0] = False
    _in_test[0] = True
    mon.restart_events()  # functions switched off in an earlier test are reported again, once, in this one


def pytest_runtest_teardown(item, nextitem):
    _in_test[0] = False
    mon.restart_events()  # code run outside tests goes to __global__ (and is switched off again after one call)


def pytest_runtest_logreport(report):
    if report.when == "call":
        _map[report.nodeid] = {"funcs": sorted(_cur), "classes": sorted(_cls), "always": _always[0],
                               "time": round(report.duration, 4), "ok": report.passed}


def pytest_sessionfinish(session, exitstatus):
    mon.set_events(TOOL, 0)
    mon.free_tool_id(TOOL)
    _map["__global__"] = {"funcs": sorted(_glob)}
    json.dump(_map, open(os.environ["COVMAP_OUT"], "w"))
