"""Planted-bug safety check for impact selection on sympy.

Bugs (as in research/ripple/mutants.py: comparison/boolean flips in functions, deleted table entries or flipped
booleans at class and module level) are planted in sympy/functions and sympy/core. Ground truth: the tests of
sympy/functions run normally (cache on) on the bugged tree; selection: dc_engine.impact.selection with the coverage map
built at the base with sympy's cache cleared before each test. A bug is missed if a failing test is not selected.
Usage: python mutants_sympy.py N_PER_KIND SEED OUT.json"""
import json, os, random, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "research", "ripple")); sys.path.insert(0, os.path.join(ROOT, "src"))
import mutants as M  # noqa: E402
from dc_engine import impact as I  # noqa: E402
S = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad"
WORK = os.path.join(S, "mut-sympy")
TARGET = "sympy/functions"
PLUG = os.path.join(S, "sympy-work")


def suite():
    out = os.path.join(S, "mut-sympy-out.json")
    if os.path.exists(out):
        os.remove(out)
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": f"{WORK}:{PLUG}", "HOME": "/tmp",
           "PYTHONDONTWRITEBYTECODE": "1", "OUT": out, "VPLUG_ALARM": "60"}  # a hang counts as a failure
    try:
        subprocess.run(["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "vplug", "--tb=no",
                        "--continue-on-collection-errors", TARGET], cwd=WORK, env=env, capture_output=True, timeout=1200)
    except subprocess.TimeoutExpired:
        return None  # the bug breaks the suite so badly that it does not finish: ground truth unknown
    try:
        return json.load(open(out))
    except (OSError, ValueError):
        return {}


def main(n, seed, out_path):
    cov = json.load(open(os.path.join(S, "cov_mut_sympy_functions.json")))
    g = lambda *a: subprocess.run(["git", *a], cwd=WORK, capture_output=True)
    g("checkout", "-q", "--", ".")
    base = suite()
    base_fail = {k for k, ok in base.items() if not ok}
    rnd = random.Random(seed)
    cands = M.candidates(WORK, "sympy", ["functions", "core"])
    plan = [(k, c) for k in ("function", "class", "module") for c in rnd.sample(cands[k], min(n, len(cands[k])))]
    rows = json.load(open(out_path)) if os.path.exists(out_path) else []
    done = {(r["file"], r["line"]) for r in rows}
    for kind, (rel, ln, op) in plan:
        if (rel, ln) in done:
            continue
        g("checkout", "-q", "--", ".")
        text = M.apply(WORK, rel, ln, op)
        sel, why = I.selection(WORK, cov, sys.executable)
        res = suite()
        selected = (set(cov) - {"__global__"}) if sel is None else set(sel)
        if res is None:
            full = sel is None or len(selected) >= len(cov) - 1
            rows.append({"kind": kind, "file": rel, "line": ln, "op": op, "code": text[:120], "killed": None,
                         "failing": [], "selected": len(selected), "covered": len(cov) - 1, "full": sel is None,
                         "missed": [], "timeout": True, "safe_by_full_selection": full, "reason": why.get("reason", "")})
            print(kind, rel, ln, "suite timed out; selected", len(selected), "of", len(cov) - 1, flush=True)
            json.dump(rows, open(out_path, "w"), indent=1)
            continue
        failing = sorted(k for k, ok in res.items() if not ok and k not in base_fail)
        missed = [f for f in failing if f not in selected and not ("::" not in f and any(s.startswith(f) for s in selected))]
        rows.append({"kind": kind, "file": rel, "line": ln, "op": op, "code": text[:120], "killed": bool(failing),
                     "failing": failing, "selected": len(selected), "covered": len(cov) - 1, "full": sel is None,
                     "missed": missed, "reason": why.get("reason", "")})
        print(kind, rel, ln, "failing", len(failing), "selected", len(selected), "MISSED" if missed else "", flush=True)
        json.dump(rows, open(out_path, "w"), indent=1)
    g("checkout", "-q", "--", ".")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])


def rescore(rows_path):
    """Selection (current dc_engine) against the stored ground truth of each planted bug (no test runs)."""
    cov = json.load(open(os.path.join(S, "cov_mut_sympy_functions.json")))
    rows = json.load(open(rows_path))
    g = lambda *a: subprocess.run(["git", *a], cwd=WORK, capture_output=True)
    for r in rows:
        g("checkout", "-q", "--", ".")
        M.apply(WORK, r["file"], r["line"], r["op"])
        sel, why = I.selection(WORK, cov, sys.executable)
        selected = (set(cov) - {"__global__"}) if sel is None else set(sel)
        r["selected"], r["full"], r["reason"] = len(selected), sel is None, why.get("reason", "")
        r["missed"] = [f for f in r["failing"] if f not in selected]
    g("checkout", "-q", "--", ".")
    json.dump(rows, open(rows_path, "w"), indent=1)
    return rows
