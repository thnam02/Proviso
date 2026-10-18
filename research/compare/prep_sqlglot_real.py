"""Real historical changes on sqlglot: for each task commit (fix), the parent tree gets the fix's source changes
(sqlglot/, not tests) and the parent's own tests are run; tests failing there and not at the parent are the ground
truth. Per commit it also builds the pytest-testmon database at the parent and records testmon's selection and
Proviso's selection for the change.

Output per commit: /home/claude/cmp/sq/<id>/{tree (git repo: HEAD = parent, working tree = parent + fix source),
base.xml, change.xml, testmondata.base, testmon_selected.txt, proviso.json}
Usage: python prep_sqlglot_real.py WORKER_INDEX N_WORKERS"""
import glob, json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
from dc_engine import impact as I  # noqa: E402

RIP = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad/ripple"
SRC = "/home/claude/sources/sqlglot"
OUT = "/home/claude/cmp/sq"
TOOLS = "/home/claude/tools/coveragepy:/home/claude/tools/pytest-testmon"
PYT = ["-q", "--tb=no", "--continue-on-collection-errors", "-p", "no:cacheprovider"]


def env(tree):
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp", "PYTHONPATH": f"{tree}:{TOOLS}",
            "PYTHONDONTWRITEBYTECODE": "1"}


def git(cwd, *a):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, capture_output=True,
                          text=True)


def one(tid):
    d = os.path.join(OUT, tid)
    if os.path.isfile(os.path.join(d, "proviso.json")):
        return
    shutil.rmtree(d, ignore_errors=True)
    tree = os.path.join(d, "tree")
    shutil.copytree(os.path.join(RIP, "trees", tid, "base"), tree, ignore=shutil.ignore_patterns("__pycache__"))
    git(tree, "init", "-q"); git(tree, "add", "-A"); git(tree, "commit", "-qm", "base")
    # testmon database at the parent (also the parent's failures)
    subprocess.run(["python3", "-m", "pytest", *PYT[:-2], "--testmon", f"--junitxml={d}/base.xml", "tests"],
                   cwd=tree, env=env(tree), capture_output=True, timeout=3600)
    shutil.move(os.path.join(tree, ".testmondata"), os.path.join(d, "testmondata.base"))
    # the fix's source changes
    fix = git(SRC, "rev-parse", tid).stdout.strip()
    for line in git(SRC, "diff", "--name-status", f"{fix}^", fix, "--", "sqlglot").stdout.splitlines():
        st, *paths = line.split("\t")
        p = paths[-1]
        if st.startswith("D"):
            if os.path.exists(os.path.join(tree, p)):
                os.remove(os.path.join(tree, p))
            continue
        if st.startswith("R") and os.path.exists(os.path.join(tree, paths[0])):
            os.remove(os.path.join(tree, paths[0]))
        os.makedirs(os.path.dirname(os.path.join(tree, p)), exist_ok=True)
        blob = subprocess.run(["git", "show", f"{fix}:{p}"], cwd=SRC, capture_output=True).stdout
        open(os.path.join(tree, p), "wb").write(blob)
    open(os.path.join(d, "change.diff"), "w").write(git(tree, "diff", "HEAD").stdout)
    # ground truth: the parent's tests on the changed source
    subprocess.run(["python3", "-m", "pytest", *PYT, "-p", "no:testmon", f"--junitxml={d}/change.xml", "tests"],
                   cwd=tree, env=env(tree), capture_output=True, timeout=3600)
    # testmon's selection (on a copy of the database: a collect-only run updates it)
    shutil.copy(os.path.join(d, "testmondata.base"), os.path.join(tree, ".testmondata"))
    r = subprocess.run(["python3", "-m", "pytest", "-q", "--co", "--testmon", "--continue-on-collection-errors",
                        "tests"], cwd=tree, env=env(tree), capture_output=True, text=True, timeout=3600)
    if "collected" not in r.stdout:
        raise RuntimeError("testmon selection failed: " + (r.stdout + r.stderr)[-500:])
    open(os.path.join(d, "testmon_selected.txt"), "w").write(
        "\n".join(l for l in r.stdout.splitlines() if "::" in l and not l.startswith(("ERROR", "FAILED"))))
    open(os.path.join(d, "testmon_co.log"), "w").write(r.stdout[-3000:])
    os.remove(os.path.join(tree, ".testmondata"))
    shutil.rmtree(os.path.join(tree, ".pytest_cache"), ignore_errors=True)
    # Proviso
    cov = json.load(open(os.path.join(RIP, f"cov2_{tid}.json")))
    sel, why = I.selection(tree, cov, "python3")
    json.dump({"selected": sel, "why": why}, open(os.path.join(d, "proviso.json"), "w"), default=list)
    print(tid, "done", flush=True)


if __name__ == "__main__":
    k, n = int(sys.argv[1]), int(sys.argv[2])
    ids = sorted(os.path.basename(p)[5:15] for p in glob.glob(os.path.join(RIP, "cov2_*.json")))
    for i, tid in enumerate(ids):
        if i % n == k:
            try:
                one(tid)
            except Exception as e:  # keep going; the commit is reported as missing
                print(tid, "ERROR", repr(e)[:300], flush=True)
