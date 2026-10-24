"""Test selectors compared with Proviso. Each takes a change (a git working tree whose HEAD is the base commit) and
returns the set of test node ids to run, out of a universe of test ids (the base coverage map's tests, in scope).

  retest_all       every test
  name_match       test files named after a changed module: test_<module>.py, or test_<package>.py for a module in
                   a subpackage (what developers and agents usually pick by hand)
  static_imports   test files whose transitive imports (static, from the source) include a changed module: the
                   file-level static technique of pytest-incremental and of import-graph RTS
  file_coverage    tests whose recorded coverage executed a line of a changed file (file-level dynamic RTS,
                   Ekstazi-style; per-test file sets read from the pytest-testmon database)
  testmon          pytest-testmon 2.2.0 (block-level dynamic RTS), its own selection (collect-only run)
  *_cc             file_coverage / testmon from a database recorded with sympy's cache cleared before each test
  func_only        Proviso without its import-time analysis: tests whose base coverage calls a changed function;
                   changes outside function bodies are ignored
  func_file        func_only, plus for a change outside function bodies every test calling any function of that file
  proviso          dc_engine.impact.selection
Changes that add a source file select everything in the coverage-based selectors (as Proviso does).
"""

from __future__ import annotations

import ast
import os
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
from dc_engine import impact as I  # noqa: E402


def git(tree, *a):
    return subprocess.run(["git", *a], cwd=tree, capture_output=True, text=True).stdout


class Change:
    """Source changes of a working tree against HEAD, restricted to the given top-level packages."""

    def __init__(self, tree: str, packages: list[str]):
        self.tree = tree
        diff = git(tree, "diff", "-U0", "HEAD", "--", *packages)
        self.old_lines = {f: ls for f, ls in I._changed_old_lines(diff).items() if not I._is_test_path(f)}
        status = git(tree, "status", "--porcelain", "-uall", "--", *packages)
        self.new_files = [l[3:] for l in status.splitlines() if l.startswith("??") and l.endswith(".py")
                          and not I._is_test_path(l[3:])]
        self.deleted = [l[3:] for l in status.splitlines() if l[:2].strip() == "D" and not I._is_test_path(l[3:])]
        self.files = sorted(set(self.old_lines) | set(self.new_files) | set(self.deleted))
        self._units = None

    def units(self):
        """(functions changed {(file, first line)}, files with changes outside function bodies)."""
        if self._units is None:
            funcs, outside = set(), set()
            for f, lines in self.old_lines.items():
                src = git(self.tree, "show", f"HEAD:{f}")
                units, _ = I._units(f, src)
                for ln in lines:
                    inner = [u for u in units if u[1] <= ln <= u[2]]
                    best = min(inner, key=lambda u: u[2] - u[1]) if inner else None
                    if best is not None and best[3]:
                        funcs.add((f, best[1]))
                    else:
                        outside.add(f)
            self._units = (funcs, outside)
        return self._units


def by_file(universe):
    out = {}
    for n in universe:
        out.setdefault(n.split("::", 1)[0], set()).add(n)
    return out


def retest_all(ch, universe, **_):
    return set(universe)


def name_match(ch, universe, top="sqlglot", **_):
    want = set()
    for f in ch.files:
        parts = f[:-3].split("/")
        stem = parts[-2] if parts[-1] == "__init__" else parts[-1]
        want.add(f"test_{stem}.py")
        pkg = parts[:-1] if parts[-1] != "__init__" else parts[:-2]
        if len(pkg) >= 2:  # a module in a subpackage: its subpackage's test file too
            want.add(f"test_{pkg[-1]}.py")
    return {n for tf, ns in by_file(universe).items() if os.path.basename(tf) in want for n in ns}


# ------------------------------------------------------------------ static import graph

def _module_index(tree, roots):
    mods = {}
    for r in roots:
        for dp, dns, fns in os.walk(os.path.join(tree, r)):
            dns[:] = [d for d in dns if d != "__pycache__"]
            for fn in fns:
                if fn.endswith(".py"):
                    rel = os.path.relpath(os.path.join(dp, fn), tree)
                    mod = rel[4:] if rel.startswith(("lib/", "src/")) else rel  # src layouts import without lib/
                    name = mod[:-3].replace("/", ".")
                    if name.endswith(".__init__"):
                        name = name[: -len(".__init__")]
                    mods[name] = rel
    return mods


def _imports(tree, rel, name, mods):
    try:
        mod = ast.parse(open(os.path.join(tree, rel), encoding="utf-8").read())
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set()
    is_pkg = rel.endswith("__init__.py")
    out = set()

    def add(dotted):  # importing a.b.c runs a, a.b and a.b.c
        parts = dotted.split(".")
        for i in range(1, len(parts) + 1):
            m = ".".join(parts[:i])
            if m in mods:
                out.add(m)

    for node in ast.walk(mod):
        if isinstance(node, ast.Import):
            for a in node.names:
                add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = name.split(".") if is_pkg else name.split(".")[:-1]
                base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            add(target)
            for a in node.names:
                if f"{target}.{a.name}" in mods:
                    add(f"{target}.{a.name}")
    return out


_GRAPH = {}


def static_imports(ch, universe, roots=("sqlglot", "tests"), **_):
    key = (ch.tree, tuple(roots))
    if key not in _GRAPH:
        # the graph of the base commit (imports rarely change in a fix; a new import is in the new file anyway)
        mods = _module_index(ch.tree, roots)
        _GRAPH[key] = (mods, {m: _imports(ch.tree, rel, m, mods) for m, rel in mods.items()})
    mods, deps = _GRAPH[key]
    changed = {m for m, rel in mods.items() if rel in ch.files}
    if ch.new_files:
        return set(universe)
    rel2mod = {rel: m for m, rel in mods.items()}
    memo = {}

    def closure(m):
        if m in memo:
            return memo[m]
        seen, stack = set(), [m]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend(deps.get(x, ()))
        memo[m] = seen
        return seen

    out = set()
    for tf, ns in by_file(universe).items():
        m = rel2mod.get(tf)
        if m is None or closure(m) & changed:
            out |= ns
    return out


# ------------------------------------------------------------------ dynamic, from pytest-testmon's records

_TM = {}


def testmon_files(db):
    if db not in _TM:
        c = sqlite3.connect(db)
        rows = c.execute("select te.test_name, fp.filename from test_execution te "
                         "join test_execution_file_fp x on x.test_execution_id = te.id "
                         "join file_fp fp on fp.id = x.fingerprint_id").fetchall()
        m = {}
        for t, f in rows:
            m.setdefault(t, set()).add(f)
        _TM[db] = m
        c.close()
    return _TM[db]


def file_coverage(ch, universe, testmon_db=None, **_):
    if ch.new_files:
        return set(universe)
    files = testmon_files(testmon_db)
    changed = set(ch.files)
    return {n for n in universe if files.get(n, set()) & changed}


def testmon(ch, universe, testmon_selected=None, **_):
    return set(testmon_selected) & set(universe)


# the same two, from a testmon database recorded with sympy's cache cleared before every test (sympy only)
def file_coverage_cc(ch, universe, testmon_db_cc=None, **_):
    return file_coverage(ch, universe, testmon_db=testmon_db_cc)


def testmon_cc(ch, universe, testmon_selected_cc=None, **_):
    return set(testmon_selected_cc) & set(universe)


# ------------------------------------------------------------------ Proviso and ablations

def _always(cov, universe):
    return {n for n in universe if cov.get(n, {}).get("always")}


def func_only(ch, universe, cov=None, **_):
    if ch.new_files:
        return set(universe)
    funcs, _ = ch.units()
    if not funcs:
        return set()
    return {n for n in universe if {tuple(x) for x in cov.get(n, {}).get("funcs", [])} & funcs} | _always(cov, universe)


def func_file(ch, universe, cov=None, **_):
    if ch.new_files:
        return set(universe)
    funcs, outside = ch.units()
    out = func_only(ch, universe, cov=cov)
    if outside:
        out |= {n for n in universe if any(f in outside for f, _ in cov.get(n, {}).get("funcs", []))}
        out |= _always(cov, universe)
    return out


def proviso(ch, universe, proviso_selected="unset", cov=None, python="python3", **_):
    sel = proviso_selected
    if sel == "unset":
        sel, _ = I.selection(ch.tree, cov, python)
    return set(universe) if sel is None else set(sel) & set(universe)


SELECTORS = {"retest_all": retest_all, "name_match": name_match, "static_imports": static_imports,
             "file_coverage": file_coverage, "testmon": testmon,
             "file_coverage_cc": file_coverage_cc, "testmon_cc": testmon_cc, "func_only": func_only, "func_file": func_file,
             "proviso": proviso}


def missed(truth, selected):
    """Failing tests not selected; a test module that fails to load counts as selected if any of its tests is."""
    files = {n.split("::", 1)[0] for n in selected}
    return sorted(t for t in truth if t not in selected and not ("::" not in t and t in files))
