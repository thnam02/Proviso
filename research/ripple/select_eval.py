"""Offline check: if Proviso ran only the tests an edit can affect, how much test time is saved, and are any
failures missed?

For every saved agent run with graded results:
  edited      old-side lines of the agent's source diff (git diff HEAD -- sqlglot), mapped to code units at base
  selected    tests whose base-commit coverage (covplugin.py) calls an edited function; if a class- or module-level
              statement changed (e.g. a TRANSFORMS entry), every test that calls any function in that file;
              a new source file selects everything
  truth       existing tests that fail on the agent's final code (the graded regression set, .dc-eval-regr.xml)
Reports selected share of tests and of test time, and failing tests the selection would have missed.
"""

from __future__ import annotations

import collections
import glob
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "prefetch"))
import coverage as C  # noqa: E402  (units_of, changed_old_lines)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
from dc_engine import impact as IMP  # noqa: E402

W = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad/ripple"


def base_units(tree):
    by = collections.defaultdict(list)
    for p in glob.glob(os.path.join(tree, "sqlglot", "**", "*.py"), recursive=True):
        rel = os.path.relpath(p, tree)
        for u in C.units_of(rel, open(p, encoding="utf-8").read()):
            by[rel].append(u)
    return by


def class_spans(tree):
    import ast
    spans = collections.defaultdict(list)
    for p in glob.glob(os.path.join(tree, "sqlglot", "**", "*.py"), recursive=True):
        rel = os.path.relpath(p, tree)
        try:
            mod = ast.parse(open(p, encoding="utf-8").read())
        except SyntaxError:
            continue
        for n in ast.walk(mod):
            if isinstance(n, ast.ClassDef):
                spans[rel].append((n.lineno, n.end_lineno))
    return spans


def failing(xml):
    out = set()
    for c in ET.parse(xml).iter("testcase"):
        if any(ch.tag in ("failure", "error") for ch in c):
            parts = (c.get("classname") or "").split(".")
            out.add(f"{'/'.join(parts[:-1])}.py::{parts[-1]}::{c.get('name')}")
    return out


def main():
    rows = []
    cache = {}
    for d in sorted(glob.glob("/home/claude/eval-*")):
        if not os.path.isfile(os.path.join(d, "results.jsonl")):
            continue
        latest = {}
        for line in open(os.path.join(d, "results.jsonl")):
            r = json.loads(line)
            latest[(r["task"], r["arm"], r["rep"])] = r
        for r in latest.values():
            repo = os.path.join(r.get("run_dir") or "", "repo")
            xml = os.path.join(repo, ".dc-eval-regr.xml")
            tid = r["task"][:10]
            cov_path = os.path.join(W, f"cov2_{tid}.json")
            if not (os.path.isfile(xml) and os.path.isfile(cov_path)):
                continue
            if tid not in cache:
                cov = json.load(open(cov_path))
                tb = os.path.join(W, "trees", tid, "base")
                cache[tid] = (cov, base_units(tb), class_spans(tb))
            cov, by, cspans = cache[tid]
            diff = subprocess.run(["git", "-C", repo, "diff", "-U0", "HEAD", "--", "sqlglot"], capture_output=True,
                                  text=True).stdout
            new_files = [l[3:] for l in subprocess.run(["git", "-C", repo, "status", "--porcelain", "--", "sqlglot"],
                                                       capture_output=True, text=True).stdout.splitlines()
                         if l.startswith("??")]
            changed = C.changed_old_lines(diff)
            funcs, files_all, classes = set(), set(), set()
            for f, lines in changed.items():
                for ln in lines:
                    best = None
                    for u in by.get(f, []):
                        if u["start"] <= ln <= u["end"] and (best is None or u["end"] - u["start"] < best["end"] - best["start"]):
                            best = u
                    if best is not None and "<stmt@" in best["name"] and "." in best["name"]:
                        # class-level statement: tests that call any function inside the innermost enclosing class
                        enc = [sp for sp in cspans.get(f, []) if sp[0] <= ln <= sp[1]]
                        if enc:
                            classes.add((f,) + min(enc, key=lambda sp: sp[1] - sp[0]))
                        else:
                            files_all.add(f)
                    elif best is None or "<stmt@" in best["name"]:
                        files_all.add(f)
                    else:
                        funcs.add((f, best["start"]))
            psel, pwhy = IMP.selection(repo, cov)
            tests_only = {k: v for k, v in cov.items() if k != "__global__"}
            sel = set(tests_only) if psel is None else set(psel) & set(tests_only)
            files_all = sorted(pwhy.get("files", [])) + ([pwhy["reason"]] if psel is None else [])
            cov = tests_only
            total_t = sum(v["time"] for v in cov.values()) or 1
            sel_t = sum(cov[n]["time"] for n in sel)
            bad = failing(xml)
            known = bad & set(cov)
            missed = sorted(known - sel)
            rows.append({"eval_dir": os.path.basename(d), "task": r["task"], "arm": r["arm"], "rep": r["rep"],
                         "edited_funcs": len(funcs), "class_rules": len(classes), "file_rules": sorted(files_all), "new_files": new_files,
                         "selected": len(sel), "tests": len(cov), "time_share": round(sel_t / total_t, 3),
                         "failing": sorted(bad), "missed": missed})
    json.dump(rows, open(os.path.join(HERE, "select_eval.json"), "w"), indent=1)
    n = len(rows)
    edited = [x for x in rows if x["edited_funcs"] or x["file_rules"] or x["new_files"]]
    import statistics as st
    print(f"{n} runs ({len(edited)} with source edits)")
    print("selected share of tests: median", st.median(x["selected"] / x["tests"] for x in edited),
          "mean", round(st.mean(x["selected"] / x["tests"] for x in edited), 3))
    print("selected share of test time: median", st.median(x["time_share"] for x in edited),
          "mean", round(st.mean(x["time_share"] for x in edited), 3))
    print("runs with a failing existing test:", sum(bool(x["failing"]) for x in rows),
          "| failures missed by selection:", sum(len(x["missed"]) for x in rows))
    print("runs needing a whole-file rule:", sum(bool(x["file_rules"]) for x in edited))


if __name__ == "__main__":
    main()
