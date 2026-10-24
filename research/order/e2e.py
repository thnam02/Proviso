"""End-to-end wait until the agent sees its first failing test, in plain (untraced) seconds:
  full_default    pytest on the whole suite, its order: time until the first failing test finishes
  full_cheap      the whole suite, fastest tests first
  proviso_ranked  Proviso's warm selection time (base caches present, as after the first run of a session) + its
                  selection run in ranked order until the first failing test finishes
and the total time of a run (no stop at the first failure): full suite vs selection time + selected tests.
Per-test times: results/plain_times.json (plain runs); a test missing there (e.g. it failed to collect in the plain
run) takes its traced time scaled by the dataset's plain/traced ratio. Selection order and selected tests: as in
order.py (the same function). Warm selection time: real sqlglot commits from results/sel_time_sqlglot.json; planted
bugs timed here (selection run twice on the bugged tree, the second timed).
Usage: python e2e.py OUT.json"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import order as O  # noqa: E402

PLAIN = json.load(open(os.path.join(HERE, "results", "plain_times.json")))
WARM = {r["change"]: r["warm"] for r in json.load(open(os.path.join(HERE, "results", "sel_time_sqlglot.json")))}


def plain_cov(cov, plain):
    """cov with plain times; the scale for missing tests is the plain/traced ratio over the tests in both."""
    both = [n for n in cov if n != "__global__" and n in plain]
    ratio = sum(plain[n] for n in both) / max(1e-9, sum(cov[n].get("time", 0) or 0 for n in both))
    out = {}
    for n, v in cov.items():
        if n == "__global__":
            out[n] = v
            continue
        out[n] = {**v, "time": plain[n] if n in plain else (v.get("time", 0) or 0) * ratio}
    return out, ratio


def score(row, sel, universe, truth, cov, funcs, sel_s):
    sel = set(sel) & universe
    o = O.orders(sel, universe, cov, funcs)
    keyorder = {n: i for i, n in enumerate(cov)}
    cheap = sorted(universe, key=lambda n: (cov.get(n, {}).get("time", 0) or 0, keyorder[n]))
    tsum = lambda ns: sum(cov.get(n, {}).get("time", 0) or 0 for n in ns)
    r = {**row, "selection_s": round(sel_s, 2),
         "full_default": O.ttff(o["full_default"], truth, cov), "full_cheap": O.ttff(cheap, truth, cov),
         "proviso_ranked_tests": O.ttff(o["sel_ranked"], truth, cov),
         "full_total": tsum(universe), "proviso_total": sel_s + tsum(sel)}
    r["proviso_ranked"] = None if r["proviso_ranked_tests"] is None else sel_s + r["proviso_ranked_tests"]
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()}


def real_sqlglot():
    for d in sorted(os.listdir(O.SQ)):
        p = os.path.join(O.SQ, d)
        if not os.path.isfile(os.path.join(p, "proviso.json")):
            continue
        cov0 = json.load(open(os.path.join(O.S, "ripple", f"cov2_{d}.json")))
        ok = O.ok_filter({k for k, v in O.SEL.I._junit(os.path.join(p, "base.xml")).items() if not v})
        truth = sorted(n for n, v in O.SEL.I._junit(os.path.join(p, "change.xml")).items() if not v and ok(n))
        universe = {n for n in cov0 if n != "__global__" and ok(n)}
        cov, ratio = plain_cov(cov0, PLAIN[d])
        funcs, _ = O.SEL.Change(os.path.join(p, "tree"), ["sqlglot"]).units()
        sel = json.load(open(os.path.join(p, "proviso.json")))["selected"]
        sel = universe if sel is None else sel  # Proviso ran the full suite
        yield score({"repo": "sqlglot", "dataset": "real", "change": d, "breaks": bool(truth), "ratio": round(ratio, 3)},
                    sel, universe, truth, cov, funcs, WARM[d])


def planted(repo, work, bugs, cov0, base_fail, prefix, pkgs, tag):
    ok = O.ok_filter(base_fail)
    universe = {n for n in cov0 if n != "__global__" and ok(n) and n.startswith(prefix)}
    cov, ratio = plain_cov(cov0, PLAIN[tag])
    import shutil
    shutil.rmtree(os.path.join(work, O.SEL.I.STATE_DIR), ignore_errors=True)  # no cache from an earlier code version
    g = lambda *a: subprocess.run(["git", *a], cwd=work, capture_output=True)
    ov = {(c[0], c[1], c[2]): c for c in O.M.override_candidates(work)} if any(b["kind"] == "override" for b in bugs) \
        else {}
    for b in bugs:
        truth = sorted(t for t in (b.get("failing_set") or b.get("failing") or []) if ok(t)) if b.get("killed") else []
        if not truth:
            continue
        g("checkout", "-q", "--", ".")
        if b["kind"] == "override":
            cand = next(c for k, c in ov.items()
                        if k[0] == b["file"] and k[1] == b["line"] and b["code"].startswith(k[2] + " "))
            O.M.apply_override(work, cand)
        else:
            O.M.apply(work, b["file"], b["line"], b["op"])
        try:
            ch = O.SEL.Change(work, pkgs)
            O.SEL.I.selection(work, cov0, "python3")              # warms the caches (base snapshot, indexes)
            t = time.time()
            sel, _ = O.SEL.I.selection(work, cov0, "python3")
            sel_s = time.time() - t
            sel = universe if sel is None else sel
            yield score({"repo": repo, "dataset": "planted", "base": tag, "file": b["file"], "line": b["line"],
                         "breaks": True, "ratio": round(ratio, 3)}, sel, universe, truth, cov, ch.units()[0], sel_s)
        finally:
            g("checkout", "-q", "--", ".")


def main():
    out = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "sympy-only":   # redo only the sympy rows of an existing result file
        rows = [r for r in json.load(open(out)) if r["repo"] != "sympy"]
        cov = json.load(open(os.path.join(O.S, "cov_mut_sympy_functions.json")))
        base = {k for k, v in O.SEL.I._junit("/home/claude/cmp/sympy-mut-base.xml").items() if not v}
        rows += list(planted("sympy", os.path.join(O.S, "mut-sympy"),
                             json.load(open(os.path.join(O.ROOT, "research", "sympy", "mutants.json"))), cov, base,
                             "sympy/functions/", ["sympy"], "sympy-functions"))
        json.dump(rows, open(out, "w"), indent=1)
        return
    rows = list(real_sqlglot())
    print("real sqlglot", len(rows), flush=True)
    allbugs = json.load(open(os.path.join(O.ROOT, "research", "ripple", "mutants2_scored.json")))
    for tid in ("7f1cf60c88", "862fd55467"):
        cov = json.load(open(os.path.join(O.S, "ripple", f"cov2_{tid}.json")))
        base = {k for k, v in O.SEL.I._junit(os.path.join(O.SQ, tid, "base.xml")).items() if not v}
        rows += list(planted("sqlglot", f"/home/claude/cmp/mut-{tid}", [b for b in allbugs if b["commit"] == tid],
                             cov, base, "", ["sqlglot"], tid))
        print("planted", tid, len(rows), flush=True)
        json.dump(rows, open(out, "w"), indent=1)
    cov = json.load(open(os.path.join(O.S, "cov_mut_sympy_functions.json")))
    base = {k for k, v in O.SEL.I._junit("/home/claude/cmp/sympy-mut-base.xml").items() if not v}
    rows += list(planted("sympy", os.path.join(O.S, "mut-sympy"),
                         json.load(open(os.path.join(O.ROOT, "research", "sympy", "mutants.json"))), cov, base,
                         "sympy/functions/", ["sympy"], "sympy-functions"))
    print("planted sympy", len(rows), flush=True)
    json.dump(rows, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
