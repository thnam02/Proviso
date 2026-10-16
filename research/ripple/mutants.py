"""Planted-bug safety check for impact selection.

For a base tree, plant single-line bugs of three kinds:
  function   flip a comparison (== <-> !=, < <-> >=) or a boolean literal on one line inside a function body
  class      delete one entry line of a multi-line class-level table (e.g. TRANSFORMS, FUNCTIONS) or flip a
             class-level boolean attribute
  module     delete one entry line of a multi-line module-level table, or flip a module-level boolean
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


def candidates(tree):
    out = {"function": [], "class": [], "module": []}
    for root, _, files in os.walk(os.path.join(tree, "sqlglot")):
        for fn in files:
            if not fn.endswith(".py"):
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
    cov = json.load(open(os.path.join(W, f"cov_{prefix}.json")))
    base_fail = {k for k, v in cov.items() if not v["ok"]}
    work = os.path.join(W, f"mut-{prefix}-{seed}")
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(base, work, ignore=shutil.ignore_patterns("__pycache__"))
    g = lambda *a: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=work, capture_output=True)
    g("init", "-q"); g("add", "-A"); g("commit", "-qm", "base")
    rnd = random.Random(seed)
    cands = candidates(work)
    plan = [(k, c) for k in ("function", "class", "module") for c in rnd.sample(cands[k], min(n, len(cands[k])))]
    rows = []
    for kind, (rel, ln, op) in plan:
        g("checkout", "-q", "--", ".")
        text = apply(work, rel, ln, op)
        sel, why = I.selection(work, cov)
        failing = full_suite(work, os.path.join(work, "mut.xml")) - base_fail
        selected = set(cov) if sel is None else set(sel)
        missed = sorted(failing - selected)
        rows.append({"kind": kind, "file": rel, "line": ln, "op": op, "code": text[:120], "killed": bool(failing),
                     "failing": len(failing), "selected": len(selected), "missed": missed,
                     "rule": "full" if sel is None else ("file" if why.get("files") else "class" if why.get("classes") else "function")})
        print(kind, rel, ln, op, "failing", len(failing), "selected", len(selected), "MISSED" if missed else "", flush=True)
        json.dump(rows, open(out_path, "w"), indent=1)
    g("checkout", "-q", "--", ".")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
