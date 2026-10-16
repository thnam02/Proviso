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


def _units(path: str, src: str) -> tuple[list[tuple[str, int, int, bool]], list[tuple[int, int]]]:
    """(name, start, end, is_function) for every function and class/module-level statement; class spans."""
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
                classes.append((node.lineno, end))
                walk(node.body, prefix + node.name + ".")
            elif not isinstance(node, (ast.Import, ast.ImportFrom)):
                units.append((prefix + f"<stmt@{node.lineno}>", start, end, False))
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


def selection(root: str, covmap: dict) -> tuple[list[str] | None, dict]:
    """Test node ids to run for the current change, or None for the full suite. Second value: why."""
    pk = packages(covmap)
    if not pk:
        return None, {"reason": "empty coverage map"}
    diff = _git(root, "diff", "-U0", "HEAD", "--", *pk)
    status = _git(root, "status", "--porcelain", "--", *pk, "tests")
    new_src = [l[3:] for l in status.splitlines() if l.startswith("??") and not l[3:].startswith("tests")
               and l.endswith(".py")]
    if new_src:
        return None, {"reason": f"new source file {new_src[0]}"}
    funcs: set[tuple[str, int]] = set()
    whole_files: set[str] = set()
    classes: set[tuple[str, int, int]] = set()
    for f, lines in _changed_old_lines(diff).items():
        src = _git(root, "show", f"HEAD:{f}")
        units, cls = _units(f, src)
        for ln in lines:
            inner = [u for u in units if u[1] <= ln <= u[2]]
            best = min(inner, key=lambda u: u[2] - u[1]) if inner else None
            if best is not None and best[3]:
                funcs.add((f, best[1]))
                continue
            enc = [c for c in cls if c[0] <= ln <= c[1]]
            if best is not None and enc:
                c = min(enc, key=lambda c: c[1] - c[0])
                classes.add((f, c[0], c[1]))
            else:
                whole_files.add(f)
    sel = []
    for node, v in covmap.items():
        for f, line in v["funcs"]:
            if (f, line) in funcs or f in whole_files or any(f == c[0] and c[1] <= line <= c[2] for c in classes):
                sel.append(node)
                break
    # tests the agent added or edited always run
    touched_tests = [l[3:].strip() for l in status.splitlines() if l[3:].strip().startswith("tests")]
    extra = sorted({t for t in touched_tests if t.endswith(".py")})
    why = {"functions": len(funcs), "classes": len(classes), "files": sorted(whole_files), "agent_tests": extra}
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
            parts[i] = lead + runner + (" " + sep + tail if sep else "")
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
            parts = (c.get("classname") or "").split(".")
            node = f"{'/'.join(parts[:-1])}.py::{parts[-1]}::{c.get('name')}"
            res[node] = not any(ch.tag in ("failure", "error") for ch in c)
    except (OSError, ET.ParseError):
        pass
    return res


def run_selected(root: str, python: str) -> str:
    covmap = _asset(root, "covmap.json") or {}
    base_fail = set(_asset(root, "base_failures.json") or [])
    t0 = time.time()
    sel, why = selection(root, covmap) if covmap else (None, {"reason": "no coverage map"})
    xml = os.path.join(root, STATE_DIR, "impact.xml")
    if os.path.exists(xml):
        os.remove(xml)
    targets = ["tests"] if sel is None else sel
    if sel is not None and not sel:
        summary = ("[Proviso] Your changes do not reach any code the existing tests execute, so no existing test can "
                   f"change outcome; nothing to run (full suite: {len(covmap)} tests).")
        _log_run(root, 0, len(covmap), 0.0, [], why)
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
    old = [n for n in failing if n not in new]
    scope = (f"the {len(res)} existing tests whose code your changes reach (of {len(covmap)})" if sel is not None
             else f"the full suite ({why.get('reason', 'change could not be placed')})")
    lines = [f"[Proviso] Ran {scope} in {secs:.0f}s instead of the full suite."]
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
    lines.append(f"{sum(res.values())} passed.")
    _log_run(root, len(res), len(covmap), secs, new, why)
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


def ripple(root: str, cfg: dict[str, Any]) -> tuple[list[str], dict]:
    """Changed outputs in inheriting components, not reported before. Items are human-readable lines."""
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
        items.append((0 if now.startswith("EXC") else 1, dia,
                      f"{dia} (inherits from {src}): `{sql[:120]}` was `{was[:120]}`, now `{now[:120]}`"))
    items.sort()
    st["ripple_reported"] = sorted(seen | set(fresh))
    save_state(root, st)
    stats["ripple_reported"] = len(items)
    return [i[2] for i in items], stats


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
