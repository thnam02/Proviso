"""Selection size of every selector on the 13 real sympy fixes (research/sympy): the base tree gets the fix's source
changes, the universe is the task's subpackage tests. None of these fixes breaks an existing test (verify.py), so this
measures selection size only. With --testmon, a pytest-testmon database is recorded per task on the subpackage tests
with sympy's cache cleared before each test (as in Proviso's coverage maps), and testmon's selection is recorded.
Usage: python run_sympy_real.py OUT.json [--testmon]"""
import glob, json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sympy"))
import rts as SEL  # noqa: E402
from score import score_change  # noqa: E402
from verify import WORK, G, istest  # noqa: E402
from run_planted import env, testmon_select  # noqa: E402

EVAL = "/home/claude/eval-sy-imp"
OUT = "/home/claude/cmp/sy"
with_testmon = "--testmon" in sys.argv
rows = []
for f in sorted(glob.glob(os.path.join(EVAL, "tasks", "*.json"))):
    t = json.load(open(f))
    tid = t["id"][:10]
    subs = t["subpackages"] if isinstance(t["subpackages"], list) else eval(t["subpackages"])
    a = os.path.join(EVAL, "impact", t["id"])
    cov = json.load(open(os.path.join(a, "covmap.json")))
    base_fail = set(json.load(open(os.path.join(a, "base_failures.json"))))
    bad_files = {k for k in base_fail if "::" not in k}
    universe = {n for n in cov if n != "__global__" and any(n.startswith(s + "/") for s in subs)
                and n not in base_fail and n.split("::", 1)[0] not in bad_files}
    d = os.path.join(OUT, tid)
    tree = os.path.join(d, "tree")
    if not os.path.isdir(tree):
        shutil.copytree(f"{WORK}/{t['fix_commit'][:10]}/base", tree, ignore=shutil.ignore_patterns("__pycache__"))
        g = lambda *x: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *x], cwd=tree,
                                      capture_output=True)
        g("init", "-q"); g("add", "-A"); g("commit", "-qm", "base")
    ctx = {"roots": ("sympy",)}
    if with_testmon:
        db = os.path.join(d, "testmondata.cc")
        if not os.path.exists(db):
            subprocess.run(["git", "checkout", "-q", "--", "."], cwd=tree)
            e = env(tree)
            e["PYTHONPATH"] += ":/home/claude/cmp/plug"
            subprocess.run(["python3", "-m", "pytest", "-q", "--tb=no", "--continue-on-collection-errors", "--testmon",
                            "-p", "clearcache", *subs], cwd=tree, env=e, capture_output=True, timeout=7200)
            shutil.move(os.path.join(tree, ".testmondata"), db)
            shutil.rmtree(os.path.join(tree, ".pytest_cache"), ignore_errors=True)
    # the fix's source changes
    os.makedirs(os.path.join(tree, ".dc-engine"), exist_ok=True)
    shutil.copy(os.path.join(a, "importstate_base.json"), os.path.join(tree, ".dc-engine", "importstate_base.json"))
    for p in [p for p in G("diff", "--name-only", t["commit"], t["fix_commit"]).stdout.split()
              if p.endswith(".py") and not istest(p)]:
        open(os.path.join(tree, p), "w").write(G("show", f"{t['fix_commit']}:{p}").stdout)
    if with_testmon:
        ctx.update(testmon_db_cc=db, testmon_selected_cc=[])
        sel = []
        for s in subs:
            sel += testmon_select(tree, db, s)
        ctx["testmon_selected_cc"] = sel
    ch = SEL.Change(tree, ["sympy"])
    skip = () if with_testmon else ("file_coverage_cc", "testmon_cc")
    for r in score_change(ch, universe, [], cov, ctx, skip=("file_coverage", "testmon") + skip):
        rows.append({"repo": "sympy", "dataset": "real", "change": t["id"], "files": len(ch.files), **r})
    print(tid, " ".join(f"{r['selector']}={r['selected']}/{r['universe']}" for r in rows if r["change"] == t["id"]),
          flush=True)
    subprocess.run(["git", "checkout", "-q", "--", "."], cwd=tree)
    json.dump(rows, open(sys.argv[1], "w"), indent=1)
