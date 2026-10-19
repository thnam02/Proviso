"""Behavioural diff of a change (sqlglot): what the program does differently, as facts an LLM can read.

  import_changes(base, var)   values computed at import (module globals, class attributes) that differ between two
                              trees: found by dc_engine.importstate (fingerprints), rendered here as readable entries
                              (dict entries added/removed/changed, set/list members added/removed, other values)
  output_changes(base_out, var_out, probes)
                              probes (SQL inputs from the tests, each run in its own dialect and in every dialect that
                              inherits from it; research/ripple/replay.py) whose output differs
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src"))
from dc_engine import importstate  # noqa: E402

REPLAY = os.path.join(ROOT, "research", "ripple", "replay.py")

_DUMP = r'''
import importlib, json, re, sys
keys = json.load(open(sys.argv[1])); out = {}
ADDR = re.compile(r" at 0x[0-9a-f]+")
def r(x, n=160):
    s = ADDR.sub("", repr(x))  # function/object reprs carry memory addresses that differ between runs
    return s if len(s) <= n else s[:n] + "..."
for key in keys:
    mod, qual = key.split(":", 1)
    try:
        obj = importlib.import_module(mod)
        for part in qual.split("."):
            obj = getattr(obj, part)
    except Exception as e:
        out[key] = {"kind": "missing", "value": type(e).__name__}
        continue
    if isinstance(obj, dict):
        out[key] = {"kind": "dict", "value": {r(k, 80): r(v) for k, v in list(obj.items())[:5000]}}
    elif isinstance(obj, (set, frozenset, list, tuple)):
        out[key] = {"kind": type(obj).__name__, "value": sorted({r(v) for v in list(obj)[:5000]})}
    else:
        out[key] = {"kind": "value", "value": r(obj, 300)}
json.dump(out, open(sys.argv[2], "w"))
'''


def _env(tree):
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": tree, "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"}


def _files(tree, pkg="sqlglot"):
    return sorted(os.path.relpath(p, tree) for p in glob.glob(os.path.join(tree, pkg, "**", "*.py"), recursive=True))


def snapshot(tree):
    return importstate.snapshot(tree, _files(tree), "python3")


def _dump(tree, keys, work):
    kp, op, sp = (os.path.join(work, n) for n in ("keys.json", "vals.json", "dump.py"))
    json.dump(sorted(keys), open(kp, "w"))
    open(sp, "w").write(_DUMP)
    subprocess.run(["python3", sp, kp, op], cwd=tree, env=_env(tree), capture_output=True, timeout=600)
    try:
        return json.load(open(op))
    except (OSError, ValueError):
        return {}


def import_changes(base_tree, var_tree, base_snap, var_snap, work, max_keys=40):
    """[{key, kind, added, removed, changed | before, after}] for values that differ (fingerprint diff, then values)."""
    d = importstate.diff(base_snap, var_snap)
    keys = [k for k in d["changed"] if not k.endswith((".__mro__", ".__class__"))][:max_keys]
    if not keys:
        return []
    a, b = _dump(base_tree, keys, work), _dump(var_tree, keys, work)
    out = []
    for k in keys:
        x, y = a.get(k, {"kind": "missing", "value": None}), b.get(k, {"kind": "missing", "value": None})
        if x.get("kind") == "dict" and y.get("kind") == "dict":
            xv, yv = x["value"], y["value"]
            item = {"key": k, "kind": "dict",
                    "added": {kk: yv[kk] for kk in yv.keys() - xv.keys()},
                    "removed": {kk: xv[kk] for kk in xv.keys() - yv.keys()},
                    "changed": {kk: [xv[kk], yv[kk]] for kk in xv.keys() & yv.keys() if xv[kk] != yv[kk]}}
            if not (item["added"] or item["removed"] or item["changed"]):
                continue  # equal when rendered (e.g. a function object recreated)
        elif x.get("kind") == y.get("kind") and isinstance(x.get("value"), list):
            xs, ys = set(x["value"]), set(y["value"])
            item = {"key": k, "kind": x["kind"], "added": sorted(ys - xs), "removed": sorted(xs - ys)}
            if not (item["added"] or item["removed"]):
                continue
        else:
            if x.get("value") == y.get("value"):
                continue
            item = {"key": k, "kind": "value", "before": x.get("value"), "after": y.get("value")}
        out.append(item)
    return out


def replay(tree, probes_path, out_path):
    subprocess.run(["python3", REPLAY, "run", tree, probes_path, out_path], cwd=tree, env=_env(tree),
                   capture_output=True, timeout=1800)
    return json.load(open(out_path))


def output_changes(base_out, var_out, probes):
    out = []
    for k, v in var_out.items():
        if base_out.get(k) != v:
            src, dia, sql = probes[int(k)]
            out.append({"probe": k, "source": src or "(default)", "dialect": dia or "(default)", "input": sql.strip(),
                        "before": base_out.get(k), "after": v})
    return out
