"""Planted-bug safety check for impact selection.

For a base tree, plant single-line bugs of three kinds:
  function   flip a comparison (== <-> !=, < <-> >=) or a boolean literal on one line inside a function body
  class      delete one entry line of a multi-line class-level table (e.g. TRANSFORMS, FUNCTIONS) or flip a
             class-level boolean attribute
  module     delete one entry line of a multi-line module-level table, or flip a module-level boolean
  override   a subclass gains a copy of an inherited method with one comparison or boolean flipped
For each bug: selection (dc_engine.impact.selection with the base coverage map) vs ground truth (the full suite run on
the bugged tree; failures not present at base). A bug is "missed" if some failing test is not selected.

Usage: python research/ripple/mutants.py TASK_PREFIX N_PER_KIND SEED OUT.json
"""

from __future__ import annotations

import ast
import json
import os
import random
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
from dc_engine import impact as I  # noqa: E402

W = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad/ripple"
FLIPS = [(" == ", " != "), (" != ", " == "), (" < ", " >= "), (" >= ", " < "), ("True", "False"), ("False", "True")]


def candidates(tree, pkg="sqlglot", subdirs=None):
    out = {"function": [], "class": [], "module": []}
    roots = [os.path.join(tree, pkg, d) for d in subdirs] if subdirs else [os.path.join(tree, pkg)]
    for root, _, files in (w for r in roots for w in os.walk(r)):
        if os.sep + "tests" in root or os.sep + "benchmarks" in root:
            continue
        for fn in files:
            if not fn.endswith(".py") or fn.startswith("test_"):
                continue
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, tree)
            src = open(path, encoding="utf-8").read()
            lines = src.splitlines()
            try:
                mod = ast.parse(src)
            except SyntaxError:
                continue

            def tables(body, kind):
                for node in body:
                    if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.end_lineno and node.end_lineno - node.lineno >= 3 \
                            and isinstance(node.value, ast.Dict):
                        for ln in range(node.lineno + 1, node.end_lineno):
                            t = lines[ln - 1].strip()
                            if t.endswith(",") and ":" in t and not t.startswith(("#", "**")) and t.count("(") == t.count(")"):
                                out[kind].append((rel, ln, "delete"))
                    elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, bool) \
                            and node.lineno == node.end_lineno:
                        out[kind].append((rel, node.lineno, "flip"))
            tables(mod.body, "module")
            for node in ast.walk(mod):
                if isinstance(node, ast.ClassDef):
                    tables(node.body, "class")
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for ln in range(node.body[0].lineno, (node.end_lineno or node.lineno) + 1):
                        t = lines[ln - 1]
                        if not t.strip().startswith(("#", "\"", "'")) and any(a in t for a, _ in FLIPS):
                            out["function"].append((rel, ln, "flip"))
    return out


OVERRIDE_CODE = r'''
import inspect, json, os, sys, textwrap, importlib, random
tree = sys.argv[1]; FLIPS = json.loads(sys.argv[2]); rnd = random.Random(int(sys.argv[3]))
mods = []
for root, _, files in os.walk(os.path.join(tree, "sqlglot")):
    for fn in files:
        if fn.endswith(".py") and fn != "__main__.py":
            rel = os.path.relpath(os.path.join(root, fn), tree)[:-3].replace(os.sep, ".")
            try:
                mods.append(importlib.import_module(rel[:-9] if rel.endswith(".__init__") else rel))
            except Exception:
                pass
out = []
seen = set()
for m in mods:
    for name, S in list(vars(m).items()):
        if not isinstance(S, type) or S.__module__ != m.__name__ or id(S) in seen:
            continue
        seen.add(id(S))
        try:
            lines, start = inspect.getsourcelines(S)
        except (OSError, TypeError):
            continue
        if any(l.lstrip().startswith("class ") for l in lines[1:]):
            continue  # nested classes: keep insertion simple
        for B in S.__mro__[1:]:
            if not getattr(B, "__module__", "").startswith("sqlglot"):
                continue
            for k, f in vars(B).items():
                if not inspect.isfunction(f) or k in vars(S) or k.startswith("__"):
                    continue
                try:
                    src = textwrap.dedent(inspect.getsource(f))
                except (OSError, TypeError):
                    continue
                body = src.split("\n")
                flips = [i for i, l in enumerate(body) if i > 0 and not l.strip().startswith("#") and any(a in l for a, _ in FLIPS)]
                if flips and "super()" not in src and "__class__" not in src:
                    out.append([os.path.relpath(inspect.getsourcefile(S), tree), start + len(lines) - 1, k, B.__qualname__, src, rnd.choice(flips)])
print(json.dumps(out))
'''


def override_candidates(tree):
    r = subprocess.run([sys.executable, "-c", OVERRIDE_CODE, tree, json.dumps(FLIPS), "0"], cwd=tree,
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": tree, "HOME": "/tmp"})
    return [tuple(x) for x in json.loads(r.stdout.strip().splitlines()[-1])]


def apply_override(tree, cand):
    rel, end_line, name, base, src, flip_at = cand
    body = src.split("\n")
    for a, b in FLIPS:
        if a in body[flip_at]:
            body[flip_at] = body[flip_at].replace(a, b, 1)
            break
    path = os.path.join(tree, rel)
    lines = open(path, encoding="utf-8").read().split("\n")
    cls_line = lines[end_line - 1]
    # indent of the class body: first non-empty line after the class header
    ind = "    "
    for l in lines[end_line - 1::-1]:
        if l.strip().startswith("class "):
            ind = l[:len(l) - len(l.lstrip())] + "    "
            break
    new = [""] + [(ind + l) if l.strip() else "" for l in body]
    lines[end_line:end_line] = new
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    return f"{name} (from {base}) flipped: {body[flip_at].strip()[:80]}"


def apply(tree, rel, ln, op):
    path = os.path.join(tree, rel)
    lines = open(path, encoding="utf-8").read().split("\n")
    old = lines[ln - 1]
    if op == "delete":
        lines[ln - 1] = ""
    else:
        for a, b in FLIPS:
            if a in old:
                lines[ln - 1] = old.replace(a, b, 1)
                break
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    return old.strip()


def full_suite(tree, xml):
    if os.path.exists(xml):
        os.remove(xml)
    subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no",
                    "--continue-on-collection-errors", f"--junitxml={xml}", "tests"], cwd=tree, capture_output=True,
                   env={"PATH": "/usr/bin:/bin", "PYTHONPATH": tree, "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
                   timeout=1200)
    return {n for n, ok in I._junit(xml).items() if not ok}


def main(prefix, n, seed, out_path):
    base = os.path.join(W, "trees", prefix, "base")
    cov = json.load(open(os.path.join(W, f"cov2_{prefix}.json")))
    base_fail = {k for k, v in cov.items() if k != "__global__" and not v["ok"]}
    work = os.path.join(W, f"mut-{prefix}-{seed}")
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(base, work, ignore=shutil.ignore_patterns("__pycache__"))
    g = lambda *a: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=work, capture_output=True)
    g("init", "-q"); g("add", "-A"); g("commit", "-qm", "base")
    base_xml_fail = full_suite(work, os.path.join(work, "base.xml"))
    rnd = random.Random(seed)
    cands = candidates(work)
    plan = [(k, c) for k in ("function", "class", "module") for c in rnd.sample(cands[k], min(n, len(cands[k])))]
    ov = override_candidates(work)
    by_file = {}
    for c in ov:
        by_file.setdefault(c[0], []).append(c)
    r2 = random.Random(seed + 100)
    files = r2.sample(sorted(by_file), min(n, len(by_file)))
    plan += [("override", r2.choice(by_file[f])) for f in files]
    rows = []
    for kind, cand in plan:
        g("checkout", "-q", "--", ".")
        if kind == "override":
            text = apply_override(work, cand)
            rel, ln, op = cand[0], cand[1], "override"
        else:
            rel, ln, op = cand
            text = apply(work, rel, ln, op)
        failing = full_suite(work, os.path.join(work, "mut.xml")) - base_fail - base_xml_fail
        rows.append({"kind": kind, "file": rel, "line": ln, "op": op, "code": text[:160], "killed": bool(failing),
                     "failing_set": sorted(failing)})
        print(kind, rel, ln, op, "failing", len(failing), flush=True)
        json.dump(rows, open(out_path, "w"), indent=1)
    g("checkout", "-q", "--", ".")


def score(prefix, seed, rows_path):
    """Selection (current dc_engine.impact) against the stored full-suite failures of each planted bug."""
    work = os.path.join(W, f"mut-{prefix}-{seed}")
    cov = json.load(open(os.path.join(W, f"cov2_{prefix}.json")))
    rows = json.load(open(rows_path))
    ov = {(c[0], c[1], c[2]): c for c in override_candidates(work)} if any(r["kind"] == "override" for r in rows) else {}
    out = []
    for r in rows:
        g = subprocess.run(["git", "checkout", "-q", "--", "."], cwd=work)
        if r["kind"] == "override":
            cand = next(c for k, c in ov.items() if k[0] == r["file"] and k[1] == r["line"] and r["code"].startswith(k[2] + " "))
            apply_override(work, cand)
        else:
            apply(work, r["file"], r["line"], r["op"])
        sel, why = I.selection(work, cov, sys.executable)
        selected = (set(cov) - {"__global__"}) if sel is None else set(sel)
        missed = []
        for n in r["failing_set"]:
            if "::" not in n and n.endswith(".py"):
                ok = any(s.startswith(n) for s in selected)  # a test module that no longer loads
            else:
                ok = n in selected
            if not ok:
                missed.append(n)
        out.append({**r, "selected": len(selected), "full": sel is None, "missed": missed,
                    "reason": why.get("reason", "")})
    subprocess.run(["git", "checkout", "-q", "--", "."], cwd=work)
    return out


if __name__ == "__main__":
    if sys.argv[1] == "score":
        res = []
        for spec in sys.argv[3:]:
            prefix, seed, path = spec.split(",")
            res += [dict(x, commit=prefix) for x in score(prefix, int(seed), path)]
        json.dump(res, open(sys.argv[2], "w"), indent=1)
        for kind in ("function", "class", "module", "override"):
            k = [x for x in res if x["kind"] == kind and x["killed"]]
            if k:
                sel = sorted(x["selected"] for x in k)
                print(f"{kind:9s} caught by full suite {len(k):2d}  selection safe on {sum(not x['missed'] for x in k)}/{len(k)}"
                      f"  median selected {sel[len(sel)//2]}  full-suite fallbacks {sum(x['full'] for x in k)}")
        for x in res:
            if x["killed"] and x["missed"]:
                print("MISS", x["kind"], x["file"], x["line"], x["code"][:70], x["missed"][:3], x["reason"])
    else:
        main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
