"""Redo pytest-testmon on sympy with its selection active.

sympy's pytest config adds `-m 'not slow and not tooslow'`, and testmon 2.2.0 deactivates its selection whenever -m
is used ("selection automatically deactivated because -m was used"): the earlier sympy rows for testmon were therefore
full runs, not selections. Here every testmon database is recorded, and every selection made, with
`-o addopts= -p noslow` (plug/noslow.py drops the same slow/tooslow tests at collection), so the test set is the same
and testmon selects. The rows of testmon, testmon_cc, file_coverage and file_coverage_cc are recomputed and replace
the old ones in results/planted_sympy.json and results/real_sympy.json (all other rows are kept).

Usage: python fix_sympy_testmon.py planted|real"""
import glob, json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "research", "ripple"))
sys.path.insert(0, os.path.join(ROOT, "research", "sympy"))
import rts as SEL  # noqa: E402
import mutants as M  # noqa: E402

S = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad"
TOOLS = "/home/claude/tools/coveragepy:/home/claude/tools/pytest-testmon:/home/claude/cmp/plug"
ARGS = ["-o", "addopts=", "-p", "noslow"]
NAMES = ("file_coverage", "testmon", "file_coverage_cc", "testmon_cc")


def env(tree):
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp", "PYTHONPATH": f"{tree}:{TOOLS}",
            "PYTHONDONTWRITEBYTECODE": "1"}


def build(tree, db, targets, cc):
    if os.path.exists(db):
        return
    subprocess.run(["git", "checkout", "-q", "--", "."], cwd=tree)
    extra = ["-p", "clearcache"] if cc else []
    subprocess.run(["python3", "-m", "pytest", "-q", "--tb=no", "--continue-on-collection-errors", "--testmon",
                    *ARGS, *extra, *targets], cwd=tree, env=env(tree), capture_output=True, timeout=14400)
    shutil.move(os.path.join(tree, ".testmondata"), db)
    shutil.rmtree(os.path.join(tree, ".pytest_cache"), ignore_errors=True)


def select_q(tree, db, targets):
    shutil.copy(db, os.path.join(tree, ".testmondata"))
    r = subprocess.run(["python3", "-m", "pytest", "-q", "--co", "--testmon", "--continue-on-collection-errors",
                        *ARGS, *targets], cwd=tree, env=env(tree), capture_output=True, text=True, timeout=3600)
    os.remove(os.path.join(tree, ".testmondata"))
    shutil.rmtree(os.path.join(tree, ".pytest_cache"), ignore_errors=True)
    if "collected" not in r.stdout:
        raise RuntimeError("testmon selection failed: " + (r.stdout + r.stderr)[-600:])
    return [l for l in r.stdout.splitlines() if "::" in l and not l.startswith(("ERROR", "FAILED"))]


def check_active(tree, db, targets):
    """testmon's header must not say its selection was deactivated."""
    shutil.copy(db, os.path.join(tree, ".testmondata"))
    r = subprocess.run(["python3", "-m", "pytest", "--co", "--testmon", "--continue-on-collection-errors", *ARGS,
                        *targets], cwd=tree, env=env(tree), capture_output=True, text=True, timeout=3600)
    os.remove(os.path.join(tree, ".testmondata"))
    shutil.rmtree(os.path.join(tree, ".pytest_cache"), ignore_errors=True)
    line = next((l for l in r.stdout.splitlines() if l.startswith("testmon:")), "")
    if "deactivated" in line or not line:
        raise RuntimeError("testmon selection not active: " + line + (r.stderr[-300:]))
    return line


def rescore(rows, key, ch, universe, truth, cov, ctx):
    tsum = lambda ns: sum(cov.get(n, {}).get("time", 0) or 0 for n in ns)
    tot = tsum(universe) or 1e-9
    base = next(r for r in rows if key(r))
    out = [r for r in rows if not (key(r) and r["selector"] in NAMES)]
    for name in NAMES:
        s = SEL.SELECTORS[name](ch, universe, cov=cov, **ctx)
        out.append({**{k: v for k, v in base.items() if k not in ("selector", "selected", "time_share", "missed")},
                    "selector": name, "selected": len(s), "time_share": round(tsum(s) / tot, 4),
                    "missed": SEL.missed(truth, s)})
    return out


def planted():
    path = os.path.join(HERE, "results", "planted_sympy.json")
    rows = json.load(open(path))
    work = os.path.join(S, "mut-sympy")
    target = ["sympy/functions"]
    db, db_cc = "/home/claude/cmp/sympy-mut.v2.testmondata", "/home/claude/cmp/sympy-mut-cc.v2.testmondata"
    build(work, db, target, False)
    build(work, db_cc, target, True)
    print("planted:", check_active(work, db, target), flush=True)
    cov = json.load(open(os.path.join(S, "cov_mut_sympy_functions.json")))
    base = SEL.I._junit("/home/claude/cmp/sympy-mut-base.xml")
    base_fail = {k for k, v in base.items() if not v}
    bad = {k for k in base_fail if "::" not in k}
    ok = lambda n: n not in base_fail and n.split("::", 1)[0] not in bad
    universe = {n for n in cov if not n.startswith("__") and ok(n) and n.startswith("sympy/functions/")}
    bugs = json.load(open(os.path.join(ROOT, "research", "sympy", "mutants.json")))
    for b in bugs:
        if b.get("killed") is None:
            continue
        key = lambda r, b=b: (r["file"], r["line"]) == (b["file"], b["line"])
        if not any(key(r) for r in rows):
            continue
        subprocess.run(["git", "checkout", "-q", "--", "."], cwd=work)
        M.apply(work, b["file"], b["line"], b["op"])
        truth = sorted(t for t in b["failing"] if ok(t)) if b["killed"] else []
        ch = SEL.Change(work, ["sympy"])
        ctx = {"testmon_db": db, "testmon_db_cc": db_cc, "testmon_selected": select_q(work, db, target),
               "testmon_selected_cc": select_q(work, db_cc, target)}
        rows = rescore(rows, key, ch, universe, truth, cov, ctx)
        new = {r["selector"]: r for r in rows if key(r)}
        print(b["kind"], b["file"], b["line"], "truth", len(truth), " ".join(
            f"{n}={new[n]['selected']}{'!' if new[n]['missed'] else ''}" for n in NAMES), flush=True)
        json.dump(rows, open(path, "w"), indent=1)
    subprocess.run(["git", "checkout", "-q", "--", "."], cwd=work)


def real():
    from verify import G, istest
    path = os.path.join(HERE, "results", "real_sympy.json")
    rows = json.load(open(path))
    ev = "/home/claude/eval-sy-imp"
    for f in sorted(glob.glob(os.path.join(ev, "tasks", "*.json"))):
        t = json.load(open(f))
        tid = t["id"][:10]
        subs = t["subpackages"] if isinstance(t["subpackages"], list) else eval(t["subpackages"])
        a = os.path.join(ev, "impact", t["id"])
        cov = json.load(open(os.path.join(a, "covmap.json")))
        base_fail = set(json.load(open(os.path.join(a, "base_failures.json"))))
        bad = {k for k in base_fail if "::" not in k}
        universe = {n for n in cov if not n.startswith("__") and any(n.startswith(s + "/") for s in subs)
                    and n not in base_fail and n.split("::", 1)[0] not in bad}
        if os.path.exists(f"/home/claude/cmp/sy/{tid}/done.v2"):
            continue
        tree = f"/home/claude/cmp/sy/{tid}/tree"
        db, db_cc = f"/home/claude/cmp/sy/{tid}/testmondata.v2", f"/home/claude/cmp/sy/{tid}/testmondata.cc.v2"
        build(tree, db, subs, False)
        build(tree, db_cc, subs, True)
        check_active(tree, db, subs)
        subprocess.run(["git", "checkout", "-q", "--", "."], cwd=tree)
        for p in [p for p in G("diff", "--name-only", t["commit"], t["fix_commit"]).stdout.split()
                  if p.endswith(".py") and not istest(p)]:
            open(os.path.join(tree, p), "w").write(G("show", f"{t['fix_commit']}:{p}").stdout)
        ch = SEL.Change(tree, ["sympy"])
        ctx = {"testmon_db": db, "testmon_db_cc": db_cc, "testmon_selected": select_q(tree, db, subs),
               "testmon_selected_cc": select_q(tree, db_cc, subs)}
        key = lambda r, t=t: r["change"] == t["id"]
        rows = rescore(rows, key, ch, universe, [], cov, ctx)
        subprocess.run(["git", "checkout", "-q", "--", "."], cwd=tree)
        new = {r["selector"]: r for r in rows if key(r)}
        print(tid, " ".join(f"{n}={new[n]['selected']}/{new[n]['universe']}" for n in NAMES), flush=True)
        json.dump(rows, open(path, "w"), indent=1)
        open(f"/home/claude/cmp/sy/{tid}/done.v2", "w").close()


if __name__ == "__main__":
    {"planted": planted, "real": real}[sys.argv[1]]()
