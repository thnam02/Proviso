"""Test ordering for a coding agent: how soon does the agent see its first failure?

For each change that breaks tests (the 75 of research/compare), Proviso's selection is run in three orders and the
time until the first failing test finishes is measured from the recorded per-test times (base coverage map):
  full_default      every test, pytest's order (the agent's usual `pytest`)
  sel_default       Proviso's selection, pytest's order
  sel_cheap         Proviso's selection, fastest tests first
  sel_ranked        Proviso's selection: tests that ran a changed function first, then the rest (import-time readers,
                    class users, ...); within each group the tests that ran more of the changed functions first,
                    then the fastest
The order uses only what Proviso knows before running anything (coverage map, the diff); the failing tests are used
only to score. A failing test module (collection error) counts as found when its first selected test would run.
Usage: python order.py OUT.json"""
import glob, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "research", "compare")); sys.path.insert(0, os.path.join(ROOT, "research", "ripple"))
import rts as SEL  # noqa: E402
import mutants as M  # noqa: E402

S = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad"
SQ = "/home/claude/cmp/sq"


def ttff(order, truth, cov):
    """Seconds until the first failing test (or a test of a failing module) has run; None if none is in `order`."""
    tf, tm = set(t for t in truth if "::" in t), set(t for t in truth if "::" not in t)
    t = 0.0
    for n in order:
        t += cov.get(n, {}).get("time", 0) or 0
        if n in tf or n.split("::", 1)[0] in tm:
            return t
    return None


def orders(sel, universe, cov, funcs):
    keyorder = {n: i for i, n in enumerate(cov)}           # the coverage map is recorded in pytest's order
    tm = lambda n: cov.get(n, {}).get("time", 0) or 0
    hits = lambda n: len({tuple(x) for x in cov.get(n, {}).get("funcs", [])} & funcs)
    full = sorted(universe, key=keyorder.get)
    s = sorted(sel, key=keyorder.get)
    return {"full_default": full, "sel_default": s, "sel_cheap": sorted(s, key=lambda n: (tm(n), keyorder[n])),
            "sel_ranked": sorted(s, key=lambda n: (hits(n) == 0, -hits(n), tm(n), keyorder[n]))}


def score(row, sel, universe, truth, cov, funcs):
    sel = set(sel) & universe
    tot = sum(cov.get(n, {}).get("time", 0) or 0 for n in universe)
    out = {**row, "truth": len(truth), "selected": len(sel), "full_time": round(tot, 3),
           "sel_time": round(sum(cov.get(n, {}).get("time", 0) or 0 for n in sel), 3)}
    for k, o in orders(sel, universe, cov, funcs).items():
        v = ttff(o, truth, cov)
        out[k] = None if v is None else round(v, 3)
    return out


def ok_filter(base_fail):
    bad = {k for k in base_fail if "::" not in k}
    return lambda n: n not in base_fail and n.split("::", 1)[0] not in bad


def real_sqlglot():
    for d in sorted(glob.glob(os.path.join(SQ, "*"))):
        tid = os.path.basename(d)
        if not os.path.isfile(os.path.join(d, "proviso.json")):
            continue
        cov = json.load(open(os.path.join(S, "ripple", f"cov2_{tid}.json")))
        ok = ok_filter({k for k, v in SEL.I._junit(os.path.join(d, "base.xml")).items() if not v})
        truth = sorted(n for n, v in SEL.I._junit(os.path.join(d, "change.xml")).items() if not v and ok(n))
        if not truth:
            continue
        universe = {n for n in cov if n != "__global__" and ok(n)}
        funcs, _ = SEL.Change(os.path.join(d, "tree"), ["sqlglot"]).units()
        sel = json.load(open(os.path.join(d, "proviso.json")))["selected"]
        yield score({"repo": "sqlglot", "dataset": "real", "change": tid}, sel, universe, truth, cov, funcs)


def planted(repo, work, bugs, cov, base_fail, prefix, pkgs, tag):
    ok = ok_filter(base_fail)
    universe = {n for n in cov if n != "__global__" and ok(n) and n.startswith(prefix)}
    g = lambda *a: subprocess.run(["git", *a], cwd=work, capture_output=True)
    ov = {(c[0], c[1], c[2]): c for c in M.override_candidates(work)} if any(b["kind"] == "override" for b in bugs) \
        else {}
    for b in bugs:
        if not b.get("killed"):
            continue
        truth = sorted(t for t in (b.get("failing_set") or b.get("failing") or []) if ok(t))
        if not truth:
            continue
        g("checkout", "-q", "--", ".")
        if b["kind"] == "override":
            cand = next(c for k, c in ov.items()
                        if k[0] == b["file"] and k[1] == b["line"] and b["code"].startswith(k[2] + " "))
            M.apply_override(work, cand)
        else:
            M.apply(work, b["file"], b["line"], b["op"])
        try:
            ch = SEL.Change(work, pkgs)
            sel, _ = SEL.I.selection(work, cov, "python3")
            sel = universe if sel is None else sel
            yield score({"repo": repo, "dataset": "planted", "base": tag, "file": b["file"], "line": b["line"],
                         "kind": b["kind"]}, sel, universe, truth, cov, ch.units()[0])
        finally:
            g("checkout", "-q", "--", ".")


def main():
    out = sys.argv[1]
    rows = []
    rows += list(real_sqlglot())
    print("real sqlglot", len(rows), flush=True)
    allbugs = json.load(open(os.path.join(ROOT, "research", "ripple", "mutants2_scored.json")))
    for tid in ("7f1cf60c88", "862fd55467"):
        cov = json.load(open(os.path.join(S, "ripple", f"cov2_{tid}.json")))
        base = {k for k, v in SEL.I._junit(os.path.join(SQ, tid, "base.xml")).items() if not v}
        rows += list(planted("sqlglot", f"/home/claude/cmp/mut-{tid}", [b for b in allbugs if b["commit"] == tid],
                             cov, base, "", ["sqlglot"], tid))
        print("planted", tid, len(rows), flush=True)
        json.dump(rows, open(out, "w"), indent=1)
    cov = json.load(open(os.path.join(S, "cov_mut_sympy_functions.json")))
    base = {k for k, v in SEL.I._junit("/home/claude/cmp/sympy-mut-base.xml").items() if not v}
    rows += list(planted("sympy", os.path.join(S, "mut-sympy"),
                         json.load(open(os.path.join(ROOT, "research", "sympy", "mutants.json"))), cov, base,
                         "sympy/functions/", ["sympy"], "sympy-functions"))
    print("planted sympy", len(rows), flush=True)
    json.dump(rows, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
