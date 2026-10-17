"""Change impact for Proviso: affected-test interception and ripple replay.

Assets (built once per base commit, in .dc-engine/):
  covmap.json         {test node id: {"funcs": [[file, first line], ...], "time": s, "ok": bool}} from running the
                      suite at the base commit with a call profiler (research/ripple/covplugin.py)
  base_failures.json  test node ids (or test modules) that already fail at the base commit
  probes.json         [[source dialect, run dialect, input], ...]: inputs the test suite already contains, also run in
                      every component that inherits from the input's own (research/ripple/replay.py)
  ripple_base.json    behaviour of the base commit on those probes
  replay.py           the replay runner (repository-specific behaviour function)

Interception (PreToolUse on Bash): a broad test run (whole suite or test directory, pytest or unittest) is rewritten
to `python -m dc_engine.impact run`, which runs only the tests whose base coverage reaches the code the agent changed
(plus tests the agent added or edited), compares the result with the base failures and prints a short summary.
Anything it cannot place falls back to the full suite.

Ripple replay (Stop): the current tree is run on the probes; outputs that changed in a component other than the one
the input came from (e.g. a MySQL input run as StarRocks) are reported once.
"""

from __future__ import annotations

import ast
import glob
import json
import os
import re
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from typing import Any

STATE_DIR = ".dc-engine"
RIPPLE_MAX_ITEMS = 5

# --------------------------------------------------------------------------- change -> code units


def _git(root: str, *args: str) -> str:
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True).stdout


def _asset(root: str, name: str) -> Any:
    try:
        with open(os.path.join(root, STATE_DIR, name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _units(path: str, src: str) -> tuple[list[tuple[str, int, int, bool]], list[tuple[int, int, str]]]:
    """(name, start, end, is_function) for every function and class/module-level statement; class spans with
    their qualified names."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return [], []
    units, classes = [], []

    def walk(body, prefix):
        for node in body:
            start = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])
            end = node.end_lineno or node.lineno
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                units.append((prefix + node.name, start, end, True))
            elif isinstance(node, ast.ClassDef):
                classes.append((node.lineno, end, prefix + node.name))
                walk(node.body, prefix + node.name + ".")
            else:
                # imports and other statements run at import time; blocks (if/try/with) may define functions
                units.append((prefix + f"<stmt@{node.lineno}>", start, end, False))
                for field in ("body", "orelse", "finalbody", "handlers"):
                    sub = getattr(node, field, None)
                    if isinstance(sub, list) and sub and isinstance(sub[0], ast.AST):
                        if field == "handlers":
                            for hnd in sub:
                                walk(hnd.body, prefix)
                        else:
                            walk(sub, prefix)
    walk(tree.body, "")
    return units, classes


def _changed_old_lines(diff: str) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    cur = None
    for line in diff.splitlines():
        if line.startswith("--- "):
            cur = line[6:] if line.startswith("--- a/") else None
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+", line)
        if m and cur:
            a, b = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            out.setdefault(cur, set()).update(range(a, a + b) if b else {a, a + 1})
    return out


def packages(covmap: dict) -> list[str]:
    tops = set()
    for v in covmap.values():
        for f, _ in v["funcs"]:
            tops.add(f.split("/", 1)[0])
    return sorted(tops)


IMPORT_STATE_MAX_NAMES = 200


def _name_index(root: str, files: list[str]) -> dict[tuple[str, int], set[str]]:
    """(file, first line) of every function and lambda at HEAD -> identifiers it mentions (names, attribute names,
    string constants that look like identifiers). Calls are additionally recorded as 'call:NAME', and each function's
    own name as 'def:NAME', so callers of a function can be found."""
    idx: dict[tuple[str, int], set[str]] = {}
    for f in files:
        try:
            tree = ast.parse(_git(root, "show", f"HEAD:{f}"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                start = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])
                names = idx.setdefault((f, start), set())
                if not isinstance(node, ast.Lambda):
                    names.add(node.name)  # a test that ran the base `m` on a subclass now runs the subclass's `m`
                    names.add("def:" + node.name)
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        fn = sub.func
                        nm = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
                        if nm:
                            names.add("call:" + nm)
                    if isinstance(sub, ast.Name):
                        names.add(sub.id)
                    elif isinstance(sub, ast.Attribute):
                        names.add(sub.attr)
                    elif isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub.value.isidentifier():
                        names.add(sub.value)
    return idx


def _file_names(path: str) -> set[str]:
    """Every identifier, attribute name and identifier-like string in a file (empty if it does not parse)."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except (OSError, SyntaxError, ValueError):
        return set()
    out: set[str] = set()
    for sub in ast.walk(tree):
        if isinstance(sub, ast.Name):
            out.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.add(sub.attr)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub.value.isidentifier():
            out.add(sub.value)
    return out


def _new_top_level_defs(root: str, files: set[str]) -> set[str]:
    """Names bound by top-level `def` or `import` statements in the working tree that the base did not bind."""
    def bound(src: str) -> tuple[set[str], set[str]]:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            return set(), set()
        defs, other = set(), set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                defs.update((a.asname or a.name).split(".")[0] for a in node.names)
            else:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                        other.add(sub.id)
        return defs, other
    out: set[str] = set()
    for f in files:
        old_defs, old_other = bound(_git(root, "show", f"HEAD:{f}"))
        try:
            new_defs, _ = bound(open(os.path.join(root, f), encoding="utf-8").read())
        except OSError:
            continue
        out |= new_defs - old_defs - old_other
    return out


def _computed_lookup_patterns(root: str, files: list[str]) -> set[tuple[str, str]]:
    """(prefix, suffix) of every attribute lookup by computed name (getattr/hasattr/setattr whose name is built
    from constant parts, e.g. getattr(self, f"{key}_sql") -> ("", "_sql")). A new attribute whose name fits one can
    be reached without being named, so the classes that gain it are treated like edited classes."""
    pats: set[tuple[str, str]] = set()
    for f in files:
        try:
            tree = ast.parse(_git(root, "show", f"HEAD:{f}"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("getattr", "hasattr", "setattr")
                    and len(node.args) >= 2):
                continue
            arg = node.args[1]
            parts: list = []
            if isinstance(arg, ast.JoinedStr):
                parts = [v.value if isinstance(v, ast.Constant) else None for v in arg.values]
            elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
                stack, parts = [arg], []
                while stack:
                    n = stack.pop()
                    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
                        stack += [n.right, n.left]
                    else:
                        parts.append(n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else None)
            else:
                continue
            if not parts:
                continue
            pre = parts[0] if isinstance(parts[0], str) else ""
            suf = parts[-1] if isinstance(parts[-1], str) and len(parts) > 1 else ""
            if pre or suf:
                pats.add((pre, suf))
    return pats


def _key_class(key: str) -> str | None:
    """'pkg.mod:Cls.Inner.attr' -> 'pkg/mod.py:Cls.Inner' (the covmap's class naming)."""
    mod, qual = key.split(":", 1)
    if "." not in qual:
        return None
    return f"{mod.replace('.', '/')}.py:{qual.rsplit('.', 1)[0]}"


def _import_state_effect(root: str, covmap: dict, python: str, changed_files: set[str]
                         ) -> tuple[set[str] | None, set[str], dict]:
    """Keys ('module:Name' or 'module:Class.attr') whose import-time values the working tree changes (empty: no
    import-time effect; None: unknown), and classes to treat as edited (they gained an attribute that is looked up
    by computed name, or their bases changed)."""
    from . import importstate
    files = sorted({f for k, v in covmap.items() for f, _ in v["funcs"]})
    base = importstate.base_snapshot(root, files, python, os.path.join(root, STATE_DIR, "importstate_base.json"))
    cur = importstate.snapshot(root, files, python) if base is not None else None
    if base is None or cur is None:
        return None, set(), {"reason": "could not compare import-time state"}
    d = importstate.diff(base, cur, _new_top_level_defs(root, changed_files))
    if d["errors"]:
        return None, set(), {"reason": f"module {d['errors'][0]} no longer imports"}
    names = set(d["changed"])
    pats = _computed_lookup_patterns(root, files) if d["added_class_attrs"] else set()
    reachable = [k for k in d["added_class_attrs"]
                 if any(k.rsplit(".", 1)[-1].startswith(p) and k.rsplit(".", 1)[-1].endswith(q) for p, q in pats)]
    # a new base class or metaclass changes behaviour without changing any attribute of the class itself
    rebased = [k for k in d["changed"] if k.endswith((".__mro__", ".__class__"))]
    gained = {c for c in (_key_class(k) for k in reachable) if c}
    gained |= {c for c in (_key_class(k.rsplit(".", 1)[0] + ".x") for k in rebased) if c}
    gained |= {c.replace("/__init__.py:", ".py:") for c in gained}
    return names, gained, {"import_state_changed": d["changed"][:20], "import_state_n": len(d["changed"])}


def selection(root: str, covmap: dict, python: str | None = None) -> tuple[list[str] | None, dict]:
    """Test node ids to run for the current change, or None for the full suite. Second value: why.

    function edits    tests whose base coverage reaches the function
    class statements  tests that use the class (directly or through a subclass instance)
    module statements and edits to functions that also run at import time: the import-time state of the package is
                      compared with the base commit (importstate); if it is unchanged nothing more is needed, otherwise
                      tests reaching code that reads a changed name are added
    """
    python = python or sys.executable
    pk = packages({k: v for k, v in covmap.items() if k != "__global__"})
    if not pk:
        return None, {"reason": "empty coverage map"}
    diff = _git(root, "diff", "-U0", "HEAD", "--", *pk)
    status = _git(root, "status", "--porcelain", "--", *pk, "tests")
    new_src = [l[3:] for l in status.splitlines() if l.startswith("??") and not l[3:].startswith("tests")
               and l.endswith(".py")]
    if new_src:
        return None, {"reason": f"new source file {new_src[0]}"}
    funcs: set[tuple[str, int]] = set()
    module_level: set[str] = set()
    class_names: set[str] = set()
    for f, lines in _changed_old_lines(diff).items():
        src = _git(root, "show", f"HEAD:{f}")
        units, cls = _units(f, src)
        for ln in lines:
            inner = [u for u in units if u[1] <= ln <= u[2]]
            best = min(inner, key=lambda u: u[2] - u[1]) if inner else None
            if best is not None and best[3]:
                funcs.add((f, best[1]))
                continue
            # statements in a class body or at module level run at import: their effect is read off the
            # import-time state below
            module_level.add(f)
    glob_funcs = {tuple(x) for x in (covmap.get("__global__") or {}).get("funcs", [])}
    hit_global = sorted(funcs & glob_funcs)
    why: dict[str, Any] = {"functions": len(funcs), "files": sorted(module_level)}
    read_names: set[str] = set()
    if hit_global or module_level:
        names, gained, info = _import_state_effect(root, covmap, python, set(_changed_old_lines(diff)))
        why.update(info)
        if names is None:
            return None, why
        if len({k.rsplit(".", 1)[-1].rsplit(":", 1)[-1] for k in names}) > IMPORT_STATE_MAX_NAMES:
            return None, {**why, "reason": f"your change alters {len(names)} values computed at import time"}
        read_names = names
        class_names |= gained
    # a changed value is read by code that names it; a class attribute only through that class or a subclass,
    # so its readers count only in tests that use the class
    readers_any: set[tuple[str, int]] = set()
    readers_cls: dict[str, set[tuple[str, int]]] = {}
    test_attrs_any: set[str] = set()  # the test code itself may read a changed value
    test_attrs_cls: dict[str, set[str]] = {}
    test_file_names: dict[str, set[str]] = {}
    if read_names:
        idx = _name_index(root, sorted({f for k, v in covmap.items() for f, _ in v["funcs"]}))
        by_name: dict[str, set[tuple[str, int]]] = {}
        for fl, ns in idx.items():
            for n in ns:
                by_name.setdefault(n, set()).add(fl)
        def_name = {fl: n[4:] for fl, ns in idx.items() for n in ns if n.startswith("def:")}

        def readers_of(attr: str) -> set[tuple[str, int]]:
            # code that names the value, plus the callers of that code: a reader's result is often computed once
            # and cached (e.g. a dispatch table built from TRANSFORMS on first use), after which only its caller
            # runs, so the coverage map credits the reader to whichever test happened to run first
            direct = by_name.get(attr, set())
            calls = {"call:" + def_name[fl] for fl in direct if fl in def_name}
            callers = {fl for c in calls for fl in by_name.get(c, set())}
            return direct | callers

        for key in read_names:
            cls = _key_class(key)
            attr = key.rsplit(":", 1)[1].rsplit(".", 1)[-1]
            fl = readers_of(attr)
            if cls is None:
                readers_any |= fl
                test_attrs_any.add(attr)
            else:
                for c in {cls, cls.replace("/__init__.py:", ".py:")}:
                    readers_cls.setdefault(c, set()).update(fl)
                    test_attrs_cls.setdefault(c, set()).add(attr)
    sel = []
    any_change = bool(funcs or module_level)
    for node, v in covmap.items():
        if node == "__global__":
            continue
        if any_change and v.get("always"):
            sel.append(node)
            continue
        if class_names and class_names & set(v.get("classes") or []):
            sel.append(node)
            continue
        tf = {tuple(x) for x in v["funcs"]}
        if tf & funcs or tf & readers_any:
            sel.append(node)
            continue
        used = set(v.get("classes") or [])
        if readers_cls and any(tf & readers_cls[c] for c in used & readers_cls.keys()):
            sel.append(node)
            continue
        if test_attrs_any or test_attrs_cls:
            tfile = node.split("::", 1)[0]
            if tfile not in test_file_names:
                test_file_names[tfile] = _file_names(os.path.join(root, tfile))
            names_here = test_file_names[tfile]
            if names_here & test_attrs_any or any(names_here & test_attrs_cls[c] for c in used & test_attrs_cls.keys()):
                sel.append(node)
    # tests the agent added or edited always run
    touched_tests = [l[3:].strip() for l in status.splitlines() if l[3:].strip().startswith("tests")]
    extra = sorted({t for t in touched_tests if t.endswith(".py")})
    why["agent_tests"] = extra
    return sorted(set(sel)) + extra, why


# --------------------------------------------------------------------------- interception

BROAD_TARGETS = {"", "tests", "tests/", "./tests", "./tests/", "tests/dialects", "tests/dialects/", "."}
_SEG_SPLIT = re.compile(r"(&&|\|\||;|\n)")


def _is_broad_test(seg: str) -> bool:
    s = seg.strip()
    if re.search(r"\bmake\s+(unit|test)\b", s):
        return True
    try:
        toks = shlex.split(s)
    except ValueError:
        return False
    if not toks:
        return False
    if "pytest" in " ".join(toks[:4]):
        i = next(i for i, t in enumerate(toks) if "pytest" in t)
        rest = toks[i + 1:]
        targets, skip = [], False
        for t in rest:
            if skip:
                skip = False
                continue
            if t in ("-k", "--deselect", "-m"):
                return False  # filtered runs are already narrow
            if t in ("-p", "-c", "--ignore", "-n", "--tb", "--maxfail", "-o", "--junitxml", "-W"):
                skip = True
                continue
            if t.startswith("-") or t.startswith(("2>", ">", "|")) or t == "2>&1":
                continue
            targets.append(t)
        return all(t in BROAD_TARGETS for t in targets)
    if "unittest" in toks:
        i = toks.index("unittest")
        rest = [t for t in toks[i + 1:] if not t.startswith("-")]
        return not rest or rest[0] == "discover"
    return False


def rewrite(command: str, hook_python: str, test_python: str) -> str | None:
    """Replace each broad test invocation (up to a pipe) with the impact runner. None if nothing to do."""
    parts = _SEG_SPLIT.split(command)
    changed = False
    for i, part in enumerate(parts):
        if part in ("&&", "||", ";", "\n"):
            continue
        head, sep, tail = part.partition("|")
        if _is_broad_test(head):
            runner = f"{shlex.quote(hook_python)} -m dc_engine.impact run --python {shlex.quote(test_python)}"
            lead = re.match(r"^\s*", head).group(0)
            parts[i] = lead + runner  # the agent's filters (grep/tail) would hide the summary
            changed = True
    return "".join(parts) if changed else None


def pretool(payload: dict[str, Any], root: str, cfg: dict[str, Any]) -> dict[str, Any]:
    if not cfg.get("impact") or payload.get("tool_name") != "Bash":
        return {}
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not os.path.isfile(os.path.join(root, STATE_DIR, "covmap.json")):
        return {}
    new = rewrite(cmd, sys.executable, cfg.get("python") or sys.executable)
    if not new:
        return {}
    from .proviso import log_event
    log_event(root, {"event": "intercept", "original": cmd[:300]})
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                   "updatedInput": {**(payload.get("tool_input") or {}), "command": new}}}


def _junit(xml: str) -> dict[str, bool]:
    res = {}
    try:
        for c in ET.parse(xml).iter("testcase"):
            if not c.get("classname"):  # a test module that failed to load
                node = (c.get("name") or "").replace(".", "/") + ".py"
                res[node] = not any(ch.tag in ("failure", "error") for ch in c)
                continue
            parts = (c.get("classname") or "").split(".")
            node = f"{'/'.join(parts[:-1])}.py::{parts[-1]}::{c.get('name')}"
            res[node] = not any(ch.tag in ("failure", "error") for ch in c)
    except (OSError, ET.ParseError):
        pass
    return res


def run_selected(root: str, python: str) -> str:
    covmap = _asset(root, "covmap.json") or {}
    n_suite = len([k for k in covmap if k != "__global__"])
    base_fail = set(_asset(root, "base_failures.json") or [])
    t0 = time.time()
    sel, why = selection(root, covmap, python) if covmap else (None, {"reason": "no coverage map"})
    xml = os.path.join(root, STATE_DIR, "impact.xml")
    if os.path.exists(xml):
        os.remove(xml)
    targets = ["tests"] if sel is None else sel
    if sel is not None and not sel:
        summary = ("[Proviso] Your changes do not reach any code the existing tests execute, so no existing test can "
                   f"change outcome; nothing to run (full suite: {n_suite} tests).")
        _log_run(root, 0, n_suite, 0.0, [], why)
        return summary
    cmd = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short", "--no-header", "-rN",
           "--continue-on-collection-errors", f"--junitxml={xml}"]
    argfile = None
    if len(targets) > 200:
        argfile = os.path.join(root, STATE_DIR, "impact-args.txt")
        with open(argfile, "w", encoding="utf-8") as fh:
            fh.write("\n".join(targets))
        cmd.append(f"@{argfile}")
    else:
        cmd += targets
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    res = _junit(xml)
    secs = time.time() - t0
    failing = sorted(n for n, ok in res.items() if not ok)
    new = [n for n in failing if n not in base_fail and n.split("::")[0] not in base_fail]
    failing_modules_known = {n for n in failing if "::" not in n and n in base_fail}
    new = [n for n in new if n not in failing_modules_known]
    old = [n for n in failing if n not in new]
    if sel is not None:
        lines = [f"[Proviso] Ran the {len(res)} existing tests whose code your changes reach (of {n_suite}) in "
                 f"{secs:.0f}s instead of the full suite."]
    else:
        lines = [f"[Proviso] Ran the full suite ({why.get('reason', 'change could not be placed')}) in {secs:.0f}s."]
    if new:
        lines.append(f"NEW failures ({len(new)}), not failing before your change:")
        lines += [f"  - {n}" for n in new[:15]]
        details = _failure_details(r.stdout, new)
        if details:
            lines.append(details)
    else:
        lines.append("No new failures: every selected test that passed before your change still passes.")
    if old:
        lines.append(f"{len(old)} failure(s) that already fail at the original commit (not caused by you).")
    lines.append(f"===== {sum(res.values())} passed, {len(new)} new failed, {len(old)} pre-existing failures "
                 f"(not caused by you) in {secs:.0f}s =====")
    _log_run(root, len(res), n_suite, secs, new, why)
    return "\n".join(lines)


def _failure_details(out: str, new: list[str]) -> str:
    keep, cur, buf = [], None, []
    for line in out.splitlines():
        m = re.match(r"^_+ (.+?) _+$", line)
        if m:
            if cur and buf:
                keep.append("\n".join(buf[:25]))
            cur, buf = m.group(1), [line]
        elif cur:
            if line.startswith("=") or line.startswith("FAILED") or line.startswith("ERROR") or re.match(r"^\d+ (failed|passed)", line):
                keep.append("\n".join(buf[:25]))
                cur, buf = None, []
            else:
                buf.append(line)
    if cur and buf:
        keep.append("\n".join(buf[:25]))
    return "\n".join(keep[:5])[:6000]


def _log_run(root, ran, total, secs, new, why):
    try:
        from .proviso import log_event
        log_event(root, {"event": "impact_run", "ran": ran, "total": total, "secs": round(secs, 1),
                         "new_failures": len(new), **{k: v for k, v in why.items() if k != "agent_tests"}})
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- ripple replay


def _edit(was: str, now: str) -> tuple[str, str]:
    """The differing middle of two strings (common prefix and suffix removed)."""
    i = 0
    while i < min(len(was), len(now)) and was[i] == now[i]:
        i += 1
    j = 0
    while j < min(len(was), len(now)) - i and was[-1 - j] == now[-1 - j]:
        j += 1
    return was[i:len(was) - j], now[i:len(now) - j]


def _window(was: str, now: str, ctx: int = 40, span: int = 70) -> tuple[str, str]:
    """Both strings cut around their first difference, so the change is visible however long they are."""
    i = 0
    while i < min(len(was), len(now)) and was[i] == now[i]:
        i += 1
    start = max(0, i - ctx)

    def cut(x: str) -> str:
        return ("…" if start else "") + x[start:i + span] + ("…" if len(x) > i + span else "")
    return cut(was), cut(now)


def ripple(root: str, cfg: dict[str, Any]) -> tuple[list[dict], dict]:
    """Changed outputs in inheriting components, not reported before. Each item: component, parent, input, was, now,
    and `same`: the parent's output on the same input changed in exactly the same way (inheritance doing its job)."""
    d = os.path.join(root, STATE_DIR)
    runner, probes_p, base_p = (os.path.join(d, n) for n in ("replay.py", "probes.json", "ripple_base.json"))
    if not (os.path.isfile(runner) and os.path.isfile(probes_p) and os.path.isfile(base_p)):
        return [], {"ripple": "no assets"}
    out = os.path.join(d, "ripple_cur.json")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": root, "HOME": os.environ.get("HOME", "/tmp"),
           "PYTHONDONTWRITEBYTECODE": "1"}
    t0 = time.time()
    r = subprocess.run([cfg.get("python") or sys.executable, runner, "run", root, probes_p, out, base_p], cwd=root,
                       env=env, capture_output=True, text=True, timeout=600)
    stats = {"ripple_ms": int((time.time() - t0) * 1000)}
    if r.returncode != 0:
        stats["ripple"] = "runner error"
        return [], stats
    probes = json.load(open(probes_p))
    base = json.load(open(base_p))
    cur = json.load(open(out))
    own = {(p[0], p[2]): str(i) for i, p in enumerate(probes) if p[0] == p[1]}
    from .proviso import load_state, save_state
    st = load_state(root)
    seen = set(st.get("ripple_reported", []))
    changed = [k for k in cur if probes[int(k)][0] != probes[int(k)][1]]
    stats["ripple_changed"] = len(changed)
    fresh = [k for k in changed if k not in seen]
    items = []
    for k in fresh:
        src, dia, sql = probes[int(k)]
        was, now = base.get(k, ""), cur[k]
        pk = own.get((src, sql))
        same = pk is not None and pk in cur and _edit(base.get(pk, ""), cur[pk]) == _edit(was, now)
        items.append({"component": dia, "parent": src, "input": sql, "was": was, "now": now, "same": same,
                      "error": now.startswith("EXC")})
    items.sort(key=lambda i: (i["same"], not i["error"], i["component"]))
    st["ripple_reported"] = sorted(seen | set(fresh))
    save_state(root, st)
    stats["ripple_reported"] = len(items)
    stats["ripple_same"] = sum(i["same"] for i in items)
    return items, stats


def ripple_report(items: list[dict], max_items: int = RIPPLE_MAX_ITEMS) -> str:
    """Report for the agent: changes that differ from the parent's in full; identical inherited changes in one line
    per component, since they are usually intended but the user should still hear about them."""
    diff = [i for i in items if not i["same"]]
    same = [i for i in items if i["same"]]
    parts = ["Proviso replayed inputs from the existing tests through your changed code, in every component that "
             "inherits from the code you edited."]
    if diff:
        parts.append("These outputs changed in an inheriting component, and not in the way the parent's output "
                     "changed (or the parent's did not change at all), which is how unintended side effects look:")
        for i in diff[:max_items]:
            w, n = _window(i["was"], i["now"])
            parts.append(f"- {i['component']} (inherits from {i['parent']}), input `{i['input'][:100]}`:\n"
                         f"    was `{w}`\n    now `{n}`")
        if len(diff) > max_items:
            parts.append(f"- …and {len(diff) - max_items} more")
    if same:
        by = {}
        for i in same:
            by.setdefault((i["component"], i["parent"]), []).append(i)
        lines = []
        for (comp, par), its in sorted(by.items()):
            w, n = _window(its[0]["was"], its[0]["now"], ctx=25, span=35)
            lines.append(f"- {comp} now follows {par}'s change on {len(its)} input(s), e.g. `{w}` → `{n}`")
        parts.append("These inheriting components changed exactly as their parent did, which is usually intended:\n"
                     + "\n".join(lines))
    tail = []
    if diff:
        tail.append("Fix the unintended ones; if they are intended, say so.")
    tail.append("In your final message, tell the user which other components your change affects.")
    parts.append(" ".join(tail))
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m dc_engine.impact")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("run", help="run the tests the current change can affect")
    rp.add_argument("--python", default=sys.executable)
    rp.add_argument("--root", default=None)
    a, _rest = ap.parse_known_args(argv)
    root = a.root or _git(os.getcwd(), "rev-parse", "--show-toplevel").strip() or os.getcwd()
    text = run_selected(root, a.python)
    print(text)
    return 1 if "NEW failures" in text else 0


if __name__ == "__main__":
    raise SystemExit(main())
