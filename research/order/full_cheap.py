"""Baseline for order.py: the full suite, fastest tests first (no selection). Adds "full_cheap" to results/order.json
rows (same changes, same ground truth, same times). Usage: python full_cheap.py"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import order as O  # noqa: E402

path = os.path.join(HERE, "results", "order.json")
rows = json.load(open(path))


def put(key, universe, truth, cov):
    keyorder = {n: i for i, n in enumerate(cov)}
    o = sorted(universe, key=lambda n: (cov.get(n, {}).get("time", 0) or 0, keyorder[n]))
    v = O.ttff(o, truth, cov)
    r = next(r for r in rows if key(r))
    r["full_cheap"] = None if v is None else round(v, 3)


for d in sorted(os.listdir(O.SQ)):
    p = os.path.join(O.SQ, d)
    if not os.path.isfile(os.path.join(p, "proviso.json")):
        continue
    cov = json.load(open(os.path.join(O.S, "ripple", f"cov2_{d}.json")))
    ok = O.ok_filter({k for k, v in O.SEL.I._junit(os.path.join(p, "base.xml")).items() if not v})
    truth = sorted(n for n, v in O.SEL.I._junit(os.path.join(p, "change.xml")).items() if not v and ok(n))
    if truth:
        put(lambda r, d=d: r["dataset"] == "real" and r["change"] == d,
            {n for n in cov if not n.startswith("__") and ok(n)}, truth, cov)
allbugs = json.load(open(os.path.join(O.ROOT, "research", "ripple", "mutants2_scored.json")))
sets = [(tid, json.load(open(os.path.join(O.S, "ripple", f"cov2_{tid}.json"))),
         {k for k, v in O.SEL.I._junit(os.path.join(O.SQ, tid, "base.xml")).items() if not v}, "",
         [b for b in allbugs if b["commit"] == tid]) for tid in ("7f1cf60c88", "862fd55467")]
sets.append(("sympy-functions", json.load(open(os.path.join(O.S, "cov_mut_sympy_functions.json"))),
             {k for k, v in O.SEL.I._junit("/home/claude/cmp/sympy-mut-base.xml").items() if not v}, "sympy/functions/",
             json.load(open(os.path.join(O.ROOT, "research", "sympy", "mutants.json")))))
for tag, cov, base, prefix, bugs in sets:
    ok = O.ok_filter(base)
    universe = {n for n in cov if not n.startswith("__") and ok(n) and n.startswith(prefix)}
    for b in bugs:
        truth = sorted(t for t in (b.get("failing_set") or b.get("failing") or []) if ok(t)) if b.get("killed") else []
        if truth:
            put(lambda r, b=b, tag=tag: r["dataset"] == "planted" and r["base"] == tag and
                (r["file"], r["line"]) == (b["file"], b["line"]), universe, truth, cov)
assert all("full_cheap" in r for r in rows)
json.dump(rows, open(path, "w"), indent=1)
print("ok", len(rows))
