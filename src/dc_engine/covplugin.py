"""pytest plugin (Proviso v2): per-test coverage map that also records the code tests depend on through FIXTURE STATE.
Enable with -p covplugin_v2; output path in COVMAP_OUT; package directory in COVMAP_PKG.

A test depends on the code it runs and on code whose results reach it through shared state. Besides the test's own
call (as in covplugin_mon.py), this records:
  fixture instances   code run while pytest sets up a fixture, per instance: (fixture, scope node, parameter). A
                      class-scoped fixture runs once per class but every test of the class uses its result, so each
                      test is linked to every fixture instance in its closure (pytest's own fixture graph).
  setup/teardown      code run during a test's setup or teardown outside any fixture (plugin hooks, e.g. per-class
                      set-up in pytest_runtest_setup; fixture finalizers) is credited to the test's class, or to its
                      module for tests outside classes: such code typically runs once per class.
Output: as covplugin_mon.py, plus
  test["fx"]          keys of the fixture records the test depends on
  "__fixtures__"      {key: {"funcs": [...], "classes": [...], "always": bool}}
"__global__" keeps only code run outside any test's setup, call and teardown (imports, collection).

Recording uses sys.monitoring (PEP 669): a function is reported once per recording target and then switched off
until the target changes (sys.monitoring.restart_events); package methods stay on to record the classes they run on.
"""

import json
import os
import sys

import pytest

ROOT = os.getcwd()
PKG = os.path.join(ROOT, os.environ.get("COVMAP_PKG", "sqlglot")) + os.sep
SUBPROC = "subprocess.py"
TOOL = 3
mon = sys.monitoring
DISABLE = mon.DISABLE


class Target:
    __slots__ = ("funcs", "classes", "always")

    def __init__(self):
        self.funcs, self.classes, self.always = set(), set(), False


GLOBAL = Target()          # code run while a PACKAGE module is imported (import-time state: the snapshot's channel)
_fixtures: dict = {}      # key -> Target
_stack: list = []          # recording targets; the top one receives what runs
_map: dict = {}
_own: dict = {}            # node id -> Target of its call phase
_kind: dict = {}
_mro_cache: dict = {}


# Outside any test, code runs in one of three contexts, told apart by the module being executed at the time:
#   a package module is being imported   -> GLOBAL (import-time state, compared by the snapshot)
#   a test module is being imported      -> "<import>@FILE": every test of that file depends on it
#   anything else (plugin and conftest session set-up, collection hooks) -> "<session>": every test depends on it
_modstack: list = []       # (code object, relative file) of the modules under ROOT being executed (imports)
_watched: set = set()
SESSION = "<session>"


def _context_target():
    if _modstack:
        rel = _modstack[-1][1]
        if (ROOT + os.sep + rel).startswith(PKG):
            return GLOBAL
        if os.path.basename(rel) != "conftest.py":
            return _fixtures.setdefault(f"<import>@{rel}", Target())
    return _fixtures.setdefault(SESSION, Target())


def _target():
    return _stack[-1] if _stack else _context_target()


def _module_start(code):
    """A module under ROOT starts executing (an import): track it until it returns."""
    rel = code.co_filename[len(ROOT) + 1:]
    _modstack.append((code, rel))
    if id(code) not in _watched:
        _watched.add(id(code))
        _kind.setdefault(("watch", id(code)), code)  # keep the code object alive
        mon.set_local_events(TOOL, code, mon.events.PY_RETURN)
    mon.restart_events()


def _module_end(code, offset, arg):
    # a module that failed to import never returns: its entry is dropped when an enclosing module returns
    if any(c is code for c, _ in _modstack):
        while _modstack:
            c, _ = _modstack.pop()
            if c is code:
                break
        mon.restart_events()


def _push(t):
    _stack.append(t)
    mon.restart_events()


def _pop():
    _stack.pop()
    mon.restart_events()


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
    _kind[id(code)] = (code, k)  # keyed by identity: code objects of different files can compare equal
    return k


def _start(code, offset):
    if code.co_name == "<module>" and code.co_filename.startswith(ROOT + os.sep) and not _stack:
        _module_start(code)
    got = _kind.get(id(code))
    k = got[1] if got is not None else _classify(code)
    if k is None:
        return DISABLE
    t = _target()
    if k == "subprocess":
        t.always = True
        return DISABLE
    key, method = k
    t.funcs.add(key)
    if not method or not _stack:
        return DISABLE
    obj = sys._getframe(1).f_locals.get(code.co_varnames[0])
    if obj is not None:
        t.classes.update(_classes_of(obj if isinstance(obj, type) else type(obj)))
    return None


# ------------------------------------------------------------------------------------------------------------ keys
# A fixture instance is identified when pytest sets it up: (fixture, base id, scope node, parameter index), where the
# scope node is the node pytest itself attaches the instance to (request.node). Until pytest sets the fixture up again
# or finalises it, that instance is the fixture's current one; when a test runs, every fixture it uses is set up, so
# its current instances are exactly the ones the test uses (no reconstruction of pytest's scoping rules).

_current: dict = {}        # id(fixturedef) -> (fixturedef, key of its current instance)
_item_keys: set = set()    # fixture instances set up during the current test's setup and call


def _fx_key(fixturedef, request):
    node = getattr(request, "node", None)
    return f"{fixturedef.baseid}::{fixturedef.argname}@{node.nodeid if node is not None else ''}" \
           f"[{getattr(request, 'param_index', 0)}]"


def _outside_key(item):
    node = item.getparent(pytest.Class) or item.getparent(pytest.Module)
    return f"<setup/teardown>@{node.nodeid if node is not None else item.nodeid}"


# ------------------------------------------------------------------------------------------------------------ hooks

def _begin():
    # from the moment the plugin is loaded (-p), before conftest files import the package
    mon.use_tool_id(TOOL, "proviso-cov-v2")
    mon.register_callback(TOOL, mon.events.PY_START, _start)
    mon.register_callback(TOOL, mon.events.PY_RETURN, _module_end)
    mon.set_events(TOOL, mon.events.PY_START)


if os.environ.get("COVMAP_OUT"):
    _begin()


_BEFORE = os.environ.get("COVMAP_BEFORE_TEST", "")


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    key = _fx_key(fixturedef, request)
    _current[id(fixturedef)] = (fixturedef, key)
    _item_keys.add(key)
    _push(_fixtures.setdefault(key, Target()))
    try:
        yield
    finally:
        _pop()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_setup(item):
    _item_keys.clear()
    if _BEFORE:
        import importlib
        mod, fn = _BEFORE.split(":")
        getattr(importlib.import_module(mod), fn)()
    _push(_fixtures.setdefault(_outside_key(item), Target()))
    try:
        yield
    finally:
        _pop()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    t = _own[item.nodeid] = Target()
    _push(t)
    try:
        yield
    finally:
        _pop()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item, nextitem):
    _push(_fixtures.setdefault(_outside_key(item), Target()))
    try:
        yield
    finally:
        _pop()


_pending: dict = {}


def _closure_keys(item):
    keys = set(_item_keys)
    info = getattr(item, "_fixtureinfo", None)
    if info is not None:
        for defs in info.name2fixturedefs.values():
            for fd in defs:
                cur = _current.get(id(fd))
                if cur is not None and cur[0] is fd:
                    keys.add(cur[1])
    return keys


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    yield
    if call.when == "call":
        _pending[item.nodeid] = _closure_keys(item)   # every fixture the test used is set up and current now
    elif call.when == "teardown" and item.nodeid in _times:
        own = _own.get(item.nodeid) or Target()
        t, ok = _times[item.nodeid]
        keys = _pending.pop(item.nodeid, set()) | {_outside_key(item), SESSION,
                                                  f"<import>@{item.nodeid.split('::', 1)[0]}"}
        _map[item.nodeid] = {"funcs": sorted(own.funcs), "classes": sorted(own.classes), "always": own.always,
                             "time": t, "ok": ok, "fx": sorted(keys)}


_times: dict = {}


def pytest_runtest_logreport(report):
    if report.when == "call":
        _times[report.nodeid] = (round(report.duration, 4), report.passed)


def pytest_sessionfinish(session, exitstatus):
    mon.set_events(TOOL, 0)
    mon.free_tool_id(TOOL)
    used = {k for v in _map.values() for k in v["fx"]}
    _map["__fixtures__"] = {k: {"funcs": sorted(t.funcs), "classes": sorted(t.classes), "always": t.always}
                            for k, t in _fixtures.items() if k in used and (t.funcs or t.classes or t.always)}
    for v in _map.values():
        if "fx" in v:
            v["fx"] = [k for k in v["fx"] if k in _map["__fixtures__"]]
    _map["__global__"] = {"funcs": sorted(GLOBAL.funcs)}
    json.dump(_map, open(os.environ["COVMAP_OUT"], "w"))
