"""Verify sympy task candidates: hidden tests = tests in the merge's changed test files that fail with the base source
and pass with the fix source (both with the fix's test files). Usage: python verify.py OUT.json MERGE..."""
import json, os, shutil, subprocess, sys
SRC = "/home/claude/sources/sympy"
WORK = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad/sympy-work"
G = lambda *a: subprocess.run(["git", *a], cwd=SRC, capture_output=True, text=True)
istest = lambda p: "/tests/" in p or p.rsplit("/", 1)[-1].startswith("test_")
PLUGIN = '''import json, os, signal
_r = {}
def _alarm(signum, frame):
    raise TimeoutError("test took longer than 300 s")
signal.signal(signal.SIGALRM, _alarm)
def pytest_runtest_setup(item):
    signal.alarm(300)
def pytest_runtest_teardown(item):
    signal.alarm(0)
def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and not report.passed):
        _r[report.nodeid] = bool(report.passed or report.skipped)
def pytest_collectreport(report):
    if report.failed:
        _r[report.nodeid] = False
def pytest_sessionfinish(session, exitstatus):
    json.dump(_r, open(os.environ["OUT"], "w"))
'''


def tree(sha, dest):
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    p = subprocess.run(["git", "archive", sha], cwd=SRC, stdout=subprocess.PIPE, check=True)
    subprocess.run(["tar", "x", "-C", dest], input=p.stdout, check=True)


def run(root, targets, tag, timeout=3600):
    os.makedirs(WORK, exist_ok=True)
    open(os.path.join(WORK, "vplug.py"), "w").write(PLUGIN)
    out = os.path.join(WORK, f"out-{tag}.json")
    if os.path.exists(out):
        os.remove(out)
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": f"{root}:{WORK}", "HOME": "/tmp",
           "PYTHONDONTWRITEBYTECODE": "1", "OUT": out}
    subprocess.run(["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "vplug", "--tb=no",
                    "--continue-on-collection-errors", *targets], cwd=root, env=env, capture_output=True, timeout=timeout)
    try:
        return json.load(open(out))
    except (OSError, ValueError):
        return {}


def verify(merge):
    fix = G("rev-parse", merge).stdout.strip()
    base = G("rev-parse", fix + "^1").stdout.strip()
    files = G("diff", "--name-only", base, fix).stdout.split()
    tfiles = [f for f in files if istest(f) and f.endswith(".py")]
    d = f"{WORK}/{fix[:10]}"
    tree(fix, d + "/fix")
    tree(base, d + "/base")
    shutil.rmtree(d + "/basefix", ignore_errors=True)
    shutil.copytree(d + "/base", d + "/basefix")
    for f in tfiles:
        if os.path.exists(f"{d}/fix/{f}"):
            os.makedirs(os.path.dirname(f"{d}/basefix/{f}"), exist_ok=True)
            shutil.copy(f"{d}/fix/{f}", f"{d}/basefix/{f}")
    tfiles = [f for f in tfiles if os.path.exists(f"{d}/fix/{f}")]
    rf = run(d + "/fix", tfiles, fix[:10] + "-f")
    rb = run(d + "/basefix", tfiles, fix[:10] + "-b")
    hidden = sorted(n for n, ok in rf.items() if ok and "::" in n and not rb.get(n, False))
    return {"fix": fix, "base": base, "test_files": tfiles, "hidden": hidden, "n_fix_tests": len(rf),
            "fix_failing": sorted(n for n, ok in rf.items() if not ok)[:10]}


if __name__ == "__main__":
    out_path = sys.argv[1]
    res = json.load(open(out_path)) if os.path.exists(out_path) else {}
    for m in sys.argv[2:]:
        if m[:10] in res:
            continue
        res[m[:10]] = verify(m)
        r = res[m[:10]]
        print(m[:10], "tests", r["n_fix_tests"], "hidden", len(r["hidden"]), "fix-failing", len(r["fix_failing"]), flush=True)
        json.dump(res, open(out_path, "w"), indent=1)
