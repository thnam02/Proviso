"""Re-run Proviso's selection on every change of the sqlglot/sympy benchmark with the current engine and compare with
the stored selection (research/compare/results): failing tests missed (must stay 0) and test-time share.
Usage: python verify_rule.py OUT.json"""
import glob, json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import order as O  # noqa: E402
CMP = os.path.join(O.ROOT, "research", "compare", "results")
out = []


def check(row, tree, cov, universe, truth, stored):
    shutil.rmtree(os.path.join(tree, O.SEL.I.STATE_DIR), ignore_errors=True) if row.get("fresh") else None
    sel, why = O.SEL.I.selection(tree, cov, "python3")
    sel = universe if sel is None else set(sel) & universe
    T = lambda ns: sum(cov.get(n, {}).get("time", 0) or 0 for n in ns)
    r = {**row, "missed": O.SEL.missed(truth, sel), "time_share": round(T(sel) / (T(universe) or 1e-9), 4),
         "stored_time_share": stored["time_share"], "stored_selected": stored["selected"], "selected": len(sel)}
    out.append(r)
    flag = "MISS" if r["missed"] else ("bigger" if r["time_share"] > stored["time_share"] + 1e-4 else
                                       ("smaller" if r["time_share"] < stored["time_share"] - 1e-4 else "same"))
    print(row["id"], flag, stored["time_share"], "->", r["time_share"], flush=True)


stored = {}
for p in ("real_sqlglot.json", "planted_sqlglot_7f1c.json", "planted_sqlglot_862f.json", "planted_sympy.json", "real_sympy.json"):
    for r in json.load(open(os.path.join(CMP, p))):
        if r["selector"] == "proviso":
            stored[(r["dataset"], r.get("base") or r["repo"], r.get("change") or f"{r['file']}:{r['line']}")] = r
# real sqlglot
for d in sorted(glob.glob(os.path.join(O.SQ, "*"))):
    tid = os.path.basename(d)
    if not os.path.isfile(os.path.join(d, "proviso.json")):
        continue
    cov = json.load(open(os.path.join(O.S, "ripple", f"cov2_{tid}.json")))
    ok = O.ok_filter({k for k, v in O.SEL.I._junit(os.path.join(d, "base.xml")).items() if not v})
    truth = sorted(n for n, v in O.SEL.I._junit(os.path.join(d, "change.xml")).items() if not v and ok(n))
    universe = {n for n in cov if n != "__global__" and ok(n)}
    check({"id": f"real:{tid}"}, os.path.join(d, "tree"), cov, universe, truth, stored[("real", "sqlglot", tid)])
# planted
allbugs = json.load(open(os.path.join(O.ROOT, "research", "ripple", "mutants2_scored.json")))
sets = [(t, f"/home/claude/cmp/mut-{t}", json.load(open(os.path.join(O.S, "ripple", f"cov2_{t}.json"))),
         {k for k, v in O.SEL.I._junit(os.path.join(O.SQ, t, "base.xml")).items() if not v}, "", ["sqlglot"],
         [b for b in allbugs if b["commit"] == t]) for t in ("7f1cf60c88", "862fd55467")]
sets.append(("sympy-functions", os.path.join(O.S, "mut-sympy"), json.load(open(os.path.join(O.S, "cov_mut_sympy_functions.json"))),
             {k for k, v in O.SEL.I._junit("/home/claude/cmp/sympy-mut-base.xml").items() if not v}, "sympy/functions/",
             ["sympy"], json.load(open(os.path.join(O.ROOT, "research", "sympy", "mutants.json")))))
g = lambda w, *a: subprocess.run(["git", *a], cwd=w, capture_output=True)
for tag, work, cov, base, prefix, pkgs, bugs in sets:
    ok = O.ok_filter(base)
    universe = {n for n in cov if n != "__global__" and ok(n) and n.startswith(prefix)}
    shutil.rmtree(os.path.join(work, O.SEL.I.STATE_DIR), ignore_errors=True)
    ov = {(c[0], c[1], c[2]): c for c in O.M.override_candidates(work)} if any(b["kind"] == "override" for b in bugs) else {}
    for b in bugs:
        if b.get("killed") is None:
            continue
        key = ("planted", tag, f"{b['file']}:{b['line']}")
        if key not in stored:
            continue
        truth = sorted(t for t in (b.get("failing_set") or b.get("failing") or []) if ok(t)) if b["killed"] else []
        g(work, "checkout", "-q", "--", ".")
        if b["kind"] == "override":
            cand = next(c for k, c in ov.items() if k[0] == b["file"] and k[1] == b["line"] and b["code"].startswith(k[2] + " "))
            O.M.apply_override(work, cand)
        else:
            O.M.apply(work, b["file"], b["line"], b["op"])
        try:
            check({"id": f"{tag}:{b['file']}:{b['line']}"}, work, cov, universe, truth, stored[key])
        finally:
            g(work, "checkout", "-q", "--", ".")
json.dump(out, open(sys.argv[1], "w"), indent=1)
print("TOTAL", len(out), "misses", sum(bool(r["missed"]) for r in out), "bigger", sum(r["time_share"] > r["stored_time_share"] + 1e-4 for r in out),
      "smaller", sum(r["time_share"] < r["stored_time_share"] - 1e-4 for r in out))
