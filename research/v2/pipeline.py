"""Proviso v2 evaluation: the same protocol on every repository (fresh samples; v2 frozen before this runs).

Repositories: sqlglot, sympy, sqlalchemy (development/pilot repositories, fresh random samples) and pygments
(held out: chosen and pinned before any run, never used while developing Proviso; no fixes after its results).

Per repository (results in research/v2/results/<repo>/, scratch in $PROVISO_WORK/<repo>):
  prepare   clone at the pinned commit
  baseline  plain run of the targets: outcomes and per-test times (no tracing)
  covmap    Proviso v2 coverage map (python -m dc_engine.record: one process per test file, fixture records)
  testmon   pytest-testmon database
  nrinit    NameRTS initialised (its own instrumented run must record data, else the stage fails)
  bugs      planted single-line bugs (function / class / module), sampled per kind with a fresh seed
  truth     each bug: the targets on the bugged tree (ground truth)
  select    every selector per bug + Proviso's warm selection time
  mine      recent commits touching the package: source changes applied to the parent; which break tests
  realeval  every selector on the breaking commits (+ a sample of non-breaking), each with its own maps
  report    tables (report.md)
Usage: python pipeline.py REPO all | REPO STAGE [STAGE ...] | report-all
Env: PROVISO_WORK, PROVISO_WORKERS, PROVISO_NR_WORKERS, V2_SMOKE=1 (a few bugs/commits, to test the set-up)."""
from __future__ import annotations

import glob
import sqlite3
import json
import os
import random
import shutil
import statistics as st
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "research", "compare"))
sys.path.insert(0, os.path.join(ROOT, "research", "ripple"))
from dc_engine import impact as I  # noqa: E402
from dc_engine import record as REC  # noqa: E402
import mutants as M  # noqa: E402
import rts as SEL  # noqa: E402

SMOKE = os.environ.get("V2_SMOKE") == "1"
SEED = 2029  # fresh: the earlier studies used 0-2028

REPOS = {
    "sqlglot": dict(url="https://github.com/tobymao/sqlglot.git", commit="7f1cf60c884868a295f76dfd42745b931dd9cfbb",
                    pkg="sqlglot", targets=["tests"], mutate=None, test_dirs="tests", pythonpath=[],
                    pytest_args=[], before_test="", nr_repo="sqlglot", pip=[]),
    # a real upstream commit (the base of one of the earlier sympy fix tasks); the hash used before named a local
    # snapshot that never existed on GitHub
    "sympy": dict(url="https://github.com/sympy/sympy.git", commit="01c75e920fe969c9cbc4e2723ae7ceef89394a7f",
                  pkg="sympy", targets=["sympy/functions"], mutate=["functions", "core"], test_dirs="tests",
                  pythonpath=[], pytest_args=["-o", "addopts=", "-p", "noslow"],
                  before_test="sympy.core.cache:clear_cache", nr_repo="sympy", pip=["mpmath"]),
    "sqlalchemy": dict(url="https://github.com/sqlalchemy/sqlalchemy.git",
                       commit="10f4d1e2d706a7722ca78e79ce05b00333a7aa5b", pkg="lib/sqlalchemy",
                       targets=["test/base", "test/sql"], mutate=["sql", "engine"], test_dirs="test",
                       pythonpath=["lib"], pytest_args=[], before_test="", nr_repo="sqlalchemy",
                       pip=["greenlet", "typing-extensions"]),
    # held out: pinned before any run (2026-10-25); nothing about it was inspected while building v2
    "pygments": dict(url="https://github.com/pygments/pygments.git", commit="156d85fdd18d34427fe893527e71da91dcfb0eb5",
                     pkg="pygments", targets=["tests"], mutate=None, test_dirs="tests", pythonpath=[],
                     pytest_args=[], before_test="", nr_repo="pygments", pip=[]),
    # held out (an application, not a library): pinned 2026-10-26 before any run; only its packaging file was read
    "datasette": dict(url="https://github.com/simonw/datasette.git", commit="a8e13cc489b41f2f9a5aa691f5eb1bedf99a0e0b",
                      pkg="datasette", targets=["tests"], mutate=None, test_dirs="tests", pythonpath=[],
                      pytest_args=[], before_test="", nr_repo="datasette", pip=[],
                      # its tests hang under an address-space cap (async server, threads reserve address space):
                      # no cap for this repository; the per-run timeout still guards against runaway bugs
                      mem_limit_gb=0),
}
PER_KIND = {"function": 2, "class": 2, "module": 2} if SMOKE else {"function": 40, "class": 30, "module": 25}
SCAN_COMMITS = 6 if SMOKE else 250
REAL_BREAKING_MAX = 2 if SMOKE else 40
REAL_NONBREAKING = 2 if SMOKE else 20
SELECTORS = ["retest_all", "name_match", "static_imports", "file_coverage", "testmon", "func_only", "func_file", "proviso"]
PYTEST = ["-p", "no:randomly", "--maxfail=1000000", "--tb=no", "-q", "--continue-on-collection-errors"]
PY = sys.executable
BASE_WORK = os.environ.get("PROVISO_WORK", os.path.expanduser("~/proviso-work/v2"))
WORKERS = int(os.environ.get("PROVISO_WORKERS", max(1, (os.cpu_count() or 2) - 1)))


def _mem_gb():
    try:
        return int(next(l for l in open("/proc/meminfo") if l.startswith("MemTotal")).split()[1]) / 2 ** 20
    except (OSError, StopIteration, ValueError):
        return 8.0


NR_WORKERS = int(os.environ.get("PROVISO_NR_WORKERS", max(1, min(WORKERS, int(_mem_gb() // 5)))))
REPO = CFG = WORK = RES = None


def use(repo):
    global REPO, CFG, WORK, RES
    REPO, CFG = repo, REPOS[repo]
    WORK = os.path.join(BASE_WORK, repo)
    RES = os.path.join(HERE, "results" + ("_smoke" if SMOKE else ""), repo)
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(RES, exist_ok=True)


def log(*a):
    print(time.strftime("%H:%M:%S"), REPO, *a, flush=True)


def git(cwd, *a, check=False):
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr[-400:]}")
    return r.stdout


def env(tree, extra=(), **kw):
    paths = [os.path.join(tree, p) for p in CFG["pythonpath"]] + [tree, os.path.join(ROOT, "src"), *extra]
    paths += [x for x in os.environ.get("PROVISO_EXTRA_PATH", "").split(os.pathsep) if x]
    e = {"PATH": os.path.dirname(PY) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
         "HOME": os.environ.get("HOME", "/tmp"), "PYTHONDONTWRITEBYTECODE": "1", "PROVISO_PY": PY,
         "PYTHONPATH": os.pathsep.join(paths)}
    e.update(kw)
    return e


def jload(p, default=None):
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return default


def jdump(x, p):
    tmp = p + ".tmp"
    json.dump(x, open(tmp, "w"), indent=1)
    os.replace(tmp, p)


# ---------------------------------------------------------------------------------------------------- trees and runs

def src_repo():
    d = os.path.join(WORK, "src")
    if not os.path.isdir(os.path.join(d, ".git")):
        subprocess.run(["git", "clone", "-q", CFG["url"], d], check=True)
    return d


def make_tree(name, commit):
    d = os.path.join(WORK, "trees", name)
    if not os.path.isdir(os.path.join(d, ".git")):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", src_repo(), d], check=True)
    git(d, "checkout", "-q", "-f", commit, check=True)
    git(d, "clean", "-fdqx", "-e", ".dc-engine", "-e", ".tdad")
    return d


def reset(tree):
    git(tree, "checkout", "-q", "--", ".")
    git(tree, "clean", "-fdq", "-e", ".dc-engine", "-e", ".tdad")


PLUG = os.path.join(HERE, "plug")


def mem_limit_gb():
    """Address-space cap per test run, GB (0 = none): PROVISO_MEM_LIMIT_GB if set, else the repository's
    mem_limit_gb, else 10."""
    v = os.environ.get("PROVISO_MEM_LIMIT_GB")
    return float(v) if v not in (None, "") else float(CFG.get("mem_limit_gb", 10))


def _limit_memory():
    # a planted bug can make a test allocate without bound (one pygments bug reached 23 GB): cap the address space
    # of each test run, so such a run fails (and its tests count as failing) instead of exhausting the machine
    import resource
    lim = int(mem_limit_gb() * 2 ** 30)
    resource.setrlimit(resource.RLIMIT_AS, (lim, lim))


def run_tests(tree, out, targets=None, timeout=int(os.environ.get("PROVISO_TEST_TIMEOUT", "900"))):
    e = env(tree, [PLUG])
    e["OUTCOMES_OUT"] = out
    if os.path.exists(out):
        os.remove(out)
    # a hang raises TimeoutExpired: the caller leaves that change out (its ground truth is unknown), as before
    subprocess.run([PY, "-m", "pytest", "-p", "no:cacheprovider", "-p", "outcomes", *PYTEST, *CFG["pytest_args"],
                    *(targets or CFG["targets"])], cwd=tree, env=e, capture_output=True, timeout=timeout,
                   preexec_fn=_limit_memory if mem_limit_gb() > 0 else None)
    return jload(out, {})


def failing(outcomes):
    return {n for n, (ok, _) in outcomes.items() if not ok}


def ok_filter(base_fail):
    bad = {k for k in base_fail if "::" not in k}
    return lambda n: n not in base_fail and n.split("::", 1)[0] not in bad


# ---------------------------------------------------------------------------------------------------- base assets

def prepare():
    tree = make_tree("base", CFG["commit"])
    log("base tree", git(tree, "log", "-1", "--format=%h %cd").strip())


def baseline(tree=None, out=None):
    out = out or os.path.join(RES, "base_outcomes.json")
    if not jload(out):
        tree = tree or make_tree("base", CFG["commit"])
        t = time.time()
        r = run_tests(tree, out + ".run")
        if not r:   # e.g. a missing test dependency makes the conftest fail: stop instead of saving an empty baseline
            raise RuntimeError(f"baseline found no tests in {tree} (missing test dependency?); nothing saved")
        jdump(r, out)
        log("baseline", len(r), "tests,", len(failing(r)), "failing,", round(time.time() - t), "s")
    return jload(out)


def covmap(tree=None, out=None, workers=None):
    out = out or os.path.join(WORK, "covmap.json")
    if not jload(out):
        tree = tree or make_tree("base", CFG["commit"])
        reset(tree)
        t = time.time()
        e = env(tree, [PLUG])
        REC.record(tree, CFG["pkg"], out, PY, CFG["targets"], workers or WORKERS, CFG["before_test"],
                   ["-p", "no:randomly", *CFG["pytest_args"]], e)
        m = jload(out, {})
        n_tests = sum(1 for k in m if not k.startswith("__"))
        if not n_tests:   # never keep an empty map: a re-run would reuse it
            if os.path.exists(out):
                os.remove(out)
            raise RuntimeError(f"coverage map recorded no tests in {tree} (missing test dependency?); nothing saved")
        log("covmap v2:", n_tests, "tests,", len(m.get("__fixtures__", {})), "fixture records,",
            round(time.time() - t), "s")
    return jload(out)


def _testmon_ok(db):
    """A usable testmon database: it has recorded test executions (an interrupted or failed run leaves an empty
    file, which was then reused)."""
    try:
        c = sqlite3.connect(db)
        n = c.execute("select count(*) from test_execution").fetchone()[0]
        c.close()
        return n > 0
    except (sqlite3.Error, OSError):
        return False


def testmon(tree=None, db=None):
    """The testmon database of a tree (recorded once); None if testmon records nothing there (its two selectors,
    testmon and file_coverage, are then left out for this tree and the reason is in WORK/testmon.log)."""
    db = db or os.path.join(WORK, "testmondata.base")
    if os.path.exists(db) and not _testmon_ok(db):
        log("testmon database without executions, re-recording:", db)
        os.remove(db)
    if not os.path.exists(db):
        tree = tree or make_tree("base", CFG["commit"])
        reset(tree)
        t = time.time()
        r = subprocess.run([PY, "-m", "pytest", "--testmon", "-p", "no:randomly", "--tb=no", "-q",
                            "--continue-on-collection-errors", *CFG["pytest_args"], *CFG["targets"]], cwd=tree,
                           env=env(tree, [PLUG]), capture_output=True, text=True, timeout=7200)
        shutil.rmtree(os.path.join(tree, ".pytest_cache"), ignore_errors=True)
        made = os.path.join(tree, ".testmondata")
        if not (os.path.exists(made) and _testmon_ok(made)):
            if os.path.exists(made):
                os.remove(made)
            with open(os.path.join(WORK, "testmon.log"), "a") as fh:
                fh.write(f"== {tree} {time.strftime('%F %T')}: testmon recorded no executions\n"
                         f"{r.stdout[-3000:]}\n{r.stderr[-3000:]}\n")
            log("testmon recorded nothing in", tree, "(see testmon.log); testmon and file_coverage left out")
            return None
        shutil.move(made, db)
        log("testmon db", round(time.time() - t), "s")
    return db


def testmon_select(tree, db):
    """pytest-testmon's own selection: the tests left after its deselection (plugin plug/collected.py writes them; no
    parsing of console output, whose verbosity a project's addopts can change)."""
    shutil.copy(db, os.path.join(tree, ".testmondata"))
    out = os.path.join(WORK, f"collected_{os.path.basename(tree)}.json")
    if os.path.exists(out):
        os.remove(out)
    r = subprocess.run([PY, "-m", "pytest", "--co", "--testmon", "-q", "-p", "no:randomly", "-p", "collected",
                        "--continue-on-collection-errors", *CFG["pytest_args"], *CFG["targets"]], cwd=tree,
                       env=env(tree, [PLUG], COLLECTED_OUT=out), capture_output=True, text=True, timeout=3600)
    os.remove(os.path.join(tree, ".testmondata"))
    shutil.rmtree(os.path.join(tree, ".pytest_cache"), ignore_errors=True)
    if "deactivated" in next((l for l in r.stdout.splitlines() if l.startswith("testmon:")), ""):
        raise RuntimeError("testmon selection deactivated")
    sel = jload(out)
    if sel is None:
        raise RuntimeError("testmon selection: no collection output: " + (r.stdout + r.stderr)[-400:])
    return sel


def nr_env():
    return {"NAMERTS_HOME": os.environ.get("NAMERTS_HOME", os.path.join(BASE_WORK, "NameRTS")),
            "NAMERTS_BIN": os.path.join(HERE, "nrts-bin"), "NAMERTS_DEPS": os.environ.get("NAMERTS_DEPS", ""),
            "NAMERTS_LOGS": os.path.join(WORK, "nr-logs"), "NAMERTS_SCOPE": ",".join(CFG["targets"]),
            "NAMERTS_WORKERS": os.environ.get("NAMERTS_WORKERS", "2"), "NAMERTS_TEST_DIRS": CFG["test_dirs"]}


def namerts(action, tree, cache):
    e = {**os.environ, **nr_env(), "PROVISO_PY": PY,
         "PATH": os.path.dirname(PY) + os.pathsep + os.environ.get("PATH", ""),
         "NAMERTS_EXTRA_PATH": os.pathsep.join([os.path.join(tree, p) for p in CFG["pythonpath"]] + [PLUG] +
                                               [x for x in os.environ.get("PROVISO_EXTRA_PATH", "").split(os.pathsep) if x])}
    r = subprocess.run([PY, os.path.join(ROOT, "research", "compare", "namerts_driver.py"), action, tree, cache,
                        CFG["nr_repo"]], capture_output=True, text=True, env=e, timeout=14400)
    if action == "select":
        for line in r.stdout.splitlines():
            if line.startswith("NAMERTS_SELECTED "):
                return json.loads(line[len("NAMERTS_SELECTED "):])
        raise RuntimeError("NameRTS selection failed: " + (r.stdout + r.stderr)[-600:])
    if not os.path.isfile(os.path.join(cache, "nbdp_cache.json")):
        raise RuntimeError("NameRTS init failed: " + (r.stdout + r.stderr)[-600:])
    if not (jload(os.path.join(cache, "dependencies.json"), {}) or {}).get("dynamic_deps"):
        shutil.rmtree(cache, ignore_errors=True)
        raise RuntimeError("NameRTS's own test run recorded nothing (dynamic_deps empty): " + r.stdout[-400:])


def nr_available():
    return os.path.isdir(nr_env()["NAMERTS_HOME"])


def nrinit(tree=None, cache=None):
    if not nr_available():
        log("NameRTS not installed; skipped")
        return None
    tree = tree or make_tree("nr-base", CFG["commit"])
    cache = cache or os.path.join(WORK, "nr-cache")
    if not os.path.isfile(os.path.join(cache, "nbdp_cache.json")):
        t = time.time()
        namerts("init", tree, cache)
        log("NameRTS init", round(time.time() - t), "s")
    return cache


# ---------------------------------------------------------------------------------------------------- planted bugs

def _string_lines(path):
    import ast
    try:
        mod = ast.parse(open(path, encoding="utf-8").read())
    except (SyntaxError, UnicodeDecodeError):
        return set()
    out = set()
    for n in ast.walk(mod):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.end_lineno and n.end_lineno > n.lineno:
            out |= set(range(n.lineno, n.end_lineno + 1))
    return out


def bugs():
    out = os.path.join(RES, "bugs.json")
    if jload(out):
        return jload(out)
    tree = make_tree("base", CFG["commit"])
    cands = M.candidates(tree, CFG["pkg"], CFG["mutate"])
    skip, rnd, chosen = {}, random.Random(f"{SEED}-{REPO}"), []
    for kind, n in PER_KIND.items():
        pool = []
        for rel, ln, op in cands[kind]:
            if "/testing/" in rel or I._is_test_path(rel):
                continue
            if rel not in skip:
                skip[rel] = _string_lines(os.path.join(tree, rel))
            if ln not in skip[rel]:
                pool.append((rel, ln, op))
        rnd.shuffle(pool)
        chosen += [{"id": f"{kind}:{rel}:{ln}", "kind": kind, "file": rel, "line": ln, "op": op} for rel, ln, op in pool[:n]]
    jdump(chosen, out)
    log("bugs", {k: sum(b["kind"] == k for b in chosen) for k in PER_KIND})
    return chosen


def parallel(stage, items, workers=None):
    n = max(1, min(workers or WORKERS, len(items)))
    for i in range(n):   # logs are appended across runs: mark where this run starts
        with open(os.path.join(WORK, f"{stage}.w{i}.log"), "a") as fh:
            fh.write(f"\n===== {stage} worker {i}/{n} started {time.strftime('%F %T')} =====\n")
    procs = [subprocess.Popen([PY, os.path.abspath(__file__), REPO, "worker", stage, str(i), str(n)],
                              stdout=open(os.path.join(WORK, f"{stage}.w{i}.log"), "a"), stderr=subprocess.STDOUT)
             for i in range(n)]
    for p in procs:
        p.wait()
    log(stage, "done; worker logs in", WORK)


def merged(stage, res=None):
    rows = {}
    for p in glob.glob(os.path.join(res or RES, f"{stage}.w*.jsonl")):
        for line in open(p):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            rows[r["id"]] = r
    return rows


def append(stage, i, row):
    with open(os.path.join(RES, f"{stage}.w{i}.jsonl"), "a") as fh:
        fh.write(json.dumps(row) + "\n")


def apply_bug(tree, b):
    reset(tree)
    code = M.apply(tree, b["file"], b["line"], b["op"])
    if not git(tree, "diff", "--stat").strip():
        raise RuntimeError(f"bug not applied: {b['id']}")
    return code


def truth_worker(i, n):
    done = set(merged("truth"))
    tree = make_tree(f"w{i}", CFG["commit"])
    ok = ok_filter(failing(baseline()))
    for b in [b for b in bugs()[i::n] if b["id"] not in done]:
        try:
            code = apply_bug(tree, b)
            t = time.time()
            r = run_tests(tree, os.path.join(WORK, f"truth_w{i}.json"))
            append("truth", i, {**b, "code": code, "failing": sorted(x for x in failing(r) if ok(x)),
                                "n_tests": len(r), "secs": round(time.time() - t, 1)})
        except subprocess.TimeoutExpired:
            # the suite hangs on this bug: its ground truth is unknown, so it is left out; recorded so that a re-run
            # does not spend the timeout on it again
            append("truth", i, {**b, "failing": [], "n_tests": None, "timeout": True})
            print(b["id"], "TIMEOUT (left out)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(b["id"], "ERROR", repr(e)[:300], flush=True)
        finally:
            reset(tree)


# ---------------------------------------------------------------------------------------------------- selection

def truth_failing(b, universe):
    """Failing tests of a planted bug; a bug after which the suite produces no outcome at all (it cannot start, or the
    run is killed at the memory cap) breaks every test."""
    return sorted(universe) if b.get("n_tests") == 0 else b["failing"]


def drop_crash_rows():
    """Selection rows scored before truth_failing (a suite crash scored as breaking nothing) are removed, so the
    select stage scores them again."""
    tr = merged("truth")
    for p in glob.glob(os.path.join(RES, "select.w*.jsonl")):
        rows = [json.loads(l) for l in open(p) if l.strip()]
        keep = [r for r in rows if not (tr.get(r["id"], {}).get("n_tests") == 0 and r["truth"] == 0)]
        if len(keep) < len(rows):
            jdump_lines(keep, p)
            log("re-scoring", len(rows) - len(keep), "suite-crash bugs from", os.path.basename(p))


def universe_of(cov, base_fail):
    ok = ok_filter(base_fail)
    return {n for n in cov if not n.startswith("__") and ok(n)}


def score_all(tree, cov, universe, truth, plain, db, nr_cache, nr_tree):
    # a failing test that did not exist before the change (e.g. a new parameter id the change creates) cannot be
    # selected by any selector; it is not part of the ground truth. A file-level entry stays if its file has tests.
    files = {n.split("::", 1)[0] for n in universe}
    new = [t for t in truth if t not in universe and not ("::" not in t and t in files)]
    truth = [t for t in truth if t not in new]
    ch = SEL.Change(tree, [CFG["pkg"]])
    T = lambda ns: sum(plain.get(n, 0) for n in ns)
    tot = T(universe) or 1e-9
    roots = (CFG["pkg"], *sorted({t.split("/", 1)[0] for t in CFG["targets"]}))
    ctx = {"testmon_db": db, "roots": roots, "top": CFG["pkg"].rsplit("/", 1)[-1], "testmon_selected": []}
    tm_err = None
    if db:
        try:
            ctx["testmon_selected"] = testmon_select(tree, db)
        except Exception as e:  # noqa: BLE001  e.g. the change breaks collection under testmon
            tm_err = repr(e)[:300]
    I.selection(tree, cov, PY)                  # warm the per-commit caches, as after a session's first run
    t = time.time()
    psel, why = I.selection(tree, cov, PY)
    sel_s = time.time() - t
    ctx["proviso_selected"] = psel
    rows = {}
    for name in SELECTORS:
        if not db and name in ("testmon", "file_coverage"):
            continue
        if name == "testmon" and tm_err:
            rows[name] = {"error": tm_err}
            continue
        s = SEL.SELECTORS[name](ch, universe, cov=cov, **ctx) & universe
        rows[name] = {"selected": len(s), "time_share": round(T(s) / tot, 4), "missed": SEL.missed(truth, s)}
    rows["proviso"].update(selection_s=round(sel_s, 2), reason=why.get("reason"))
    if nr_cache:
        reset(nr_tree)
        diff = subprocess.run(["git", "diff", "HEAD"], cwd=tree, capture_output=True).stdout
        if diff:
            subprocess.run(["git", "apply", "--whitespace=nowarn"], cwd=nr_tree, input=diff, check=True)
        files = set(namerts("select", nr_tree, nr_cache))
        s = {n for n in universe if n.split("::", 1)[0] in files}
        rows["namerts"] = {"selected": len(s), "time_share": round(T(s) / tot, 4), "missed": SEL.missed(truth, s)}
        reset(nr_tree)
    return {"universe": len(universe), "full_s": round(tot, 2), "truth": len(truth), "selectors": rows,
            "new_tests_excluded": len(new)}


def select_worker(i, n):
    done, truth = set(merged("select")), merged("truth")
    tree = make_tree(f"w{i}", CFG["commit"])
    nr_cache = os.path.join(WORK, "nr-cache") if os.path.isfile(os.path.join(WORK, "nr-cache", "nbdp_cache.json")) else None
    nr_tree = make_tree(f"nr-w{i}", CFG["commit"]) if nr_cache else None
    cov, base, db = covmap(), baseline(), testmon()
    plain = {k: t for k, (ok, t) in base.items()}
    universe = universe_of(cov, failing(base))
    for b in [b for b in bugs()[i::n] if b["id"] not in done and b["id"] in truth and not truth[b["id"]].get("timeout")]:
        try:
            apply_bug(tree, b)
            r = score_all(tree, cov, universe, truth_failing(truth[b["id"]], universe), plain, db, nr_cache, nr_tree)
            append("select", i, {"id": b["id"], "kind": b["kind"], **r})
        except Exception as e:  # noqa: BLE001
            print(b["id"], "ERROR", repr(e)[:300], flush=True)
        finally:
            reset(tree)


# ---------------------------------------------------------------------------------------------------- real commits

def commits():
    out = os.path.join(RES, "commits.json")
    if jload(out):
        return jload(out)
    s = src_repo()
    paths = [f"{CFG['pkg']}/{d}" for d in CFG["mutate"]] if CFG["mutate"] else [CFG["pkg"]]
    hashes = git(s, "log", "--first-parent", "--no-merges", f"-n{SCAN_COMMITS * 3}", "--format=%H", CFG["commit"], "--",
                 *paths).split()
    cs = []
    for h in hashes:
        files = git(s, "diff", "--name-only", f"{h}^", h).split()
        src = [f for f in files if f.startswith(CFG["pkg"] + "/") and f.endswith(".py") and not I._is_test_path(f)
               and "/testing/" not in f]
        if src and len(src) <= 15:
            cs.append({"id": h[:10], "commit": h, "src": src})
        if len(cs) >= SCAN_COMMITS:
            break
    jdump(cs, out)
    log("commits to scan", len(cs))
    return cs


def apply_commit_src(tree, c):
    for f in c["src"]:
        blob = subprocess.run(["git", "show", f"{c['commit']}:{f}"], cwd=tree, capture_output=True)
        p = os.path.join(tree, f)
        if blob.returncode:
            if os.path.exists(p):
                os.remove(p)
        else:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(blob.stdout)


def mine_worker(i, n):
    done = set(merged("mine"))
    for c in [c for c in commits()[i::n] if c["id"] not in done]:
        tree = make_tree(f"w{i}", c["commit"] + "^")
        try:
            base = run_tests(tree, os.path.join(WORK, f"mine_b{i}.json"))
            apply_commit_src(tree, c)
            ch = run_tests(tree, os.path.join(WORK, f"mine_c{i}.json"))
            ok = ok_filter(failing(base))
            append("mine", i, {"id": c["id"], "commit": c["commit"], "src": c["src"],
                               "failing": sorted(x for x in failing(ch) if ok(x)), "n_tests": len(base)})
        except subprocess.TimeoutExpired:   # left out of the real set (n_tests 0), not retried
            append("mine", i, {"id": c["id"], "commit": c["commit"], "src": c["src"], "failing": [], "n_tests": 0,
                               "timeout": True})
            print(c["id"], "TIMEOUT (left out)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(c["id"], "ERROR", repr(e)[:300], flush=True)
        finally:
            reset(tree)


def real_set():
    """Sampled real commits. A commit counts only if the suite runs at its parent in this environment (at least half
    of the base commit's tests): older history stops running past some commit (Python and dependency versions), and
    such a commit's empty runs say nothing. The sample order is the same as before this filter, so repositories
    whose commits all run keep the same set."""
    m = sorted(merged("mine").values(), key=lambda r: r["id"])
    rnd = random.Random(f"{SEED}-{REPO}-real")
    brk, rest = [r for r in m if r["failing"]], [r for r in m if not r["failing"]]
    rnd.shuffle(brk)
    rnd.shuffle(rest)
    need = 0.5 * len(jload(os.path.join(RES, "base_outcomes.json"), {}) or {})
    runs = lambda r: r.get("n_tests", 0) >= need
    return [r for r in brk if runs(r)][:REAL_BREAKING_MAX] + [r for r in rest if runs(r)][:REAL_NONBREAKING]


def realeval_worker(i, n):
    done = set(merged("realeval"))
    for r in [r for r in real_set()[i::n] if r["id"] not in done]:
        parent, d = r["commit"] + "^", os.path.join(WORK, "real", r["id"])
        os.makedirs(d, exist_ok=True)
        tree = make_tree(f"w{i}", parent)
        try:
            base = baseline(tree, os.path.join(d, "base_outcomes.json"))
            cov = covmap(tree, os.path.join(d, "covmap.json"), max(1, WORKERS // NR_WORKERS))
            db = testmon(tree, os.path.join(d, "testmondata"))
            nr_cache = nr_tree = None
            if nr_available():
                nr_tree = make_tree(f"nr-w{i}", parent)
                nr_cache = nrinit(nr_tree, os.path.join(d, "nr-cache"))
            plain = {k: t for k, (ok, t) in base.items()}
            universe = universe_of(cov, failing(base))
            reset(tree)
            apply_commit_src(tree, r)
            res = score_all(tree, cov, universe, r["failing"], plain, db, nr_cache, nr_tree)
            append("realeval", i, {"id": r["id"], "breaks": bool(r["failing"]), **res})
        except Exception as e:  # noqa: BLE001
            print(r["id"], "ERROR", repr(e)[:400], flush=True)
        finally:
            reset(tree)


# ---------------------------------------------------------------------------------------------------- flaky tests

DFL = "deflake2"   # rows of the flaky-test check; "deflake" rows (first version: re-ran test ids, which pytest cannot
                   # always address, e.g. SQLAlchemy's per-backend classes, and then counted unrun tests as passing)
                   # are ignored


def _rerun_targets(names):
    """pytest targets: the files of the failing tests (test ids are not always addressable on the command line: a
    test class generated at collection, a parameter id; one unknown id makes pytest run nothing)."""
    out = []
    for n in names:
        f = n.split("::", 1)[0]
        if f not in out:
            out.append(f)
    return out


def _still_failing(names, out):
    """The failures that are not shown flaky: a test is flaky only if it ran again and passed; a test absent from the
    re-run counts as failing (unknown is not evidence of flakiness). A file-level entry (collection error) is flaky
    only if the file's tests ran and all passed."""
    conf = []
    for t in names:
        if t in out:
            if not out[t][0]:
                conf.append(t)
            continue
        f = t.split("::", 1)[0]
        ran = [ok for n, (ok, _) in out.items() if n.split("::", 1)[0] == f]
        if not ran or not all(ran):
            conf.append(t)
    return sorted(conf)


def deflake_worker(i, n):
    """Re-run each change's failing tests once more on the changed tree; a test counts as broken by the change only
    if it fails again. Tests that pass on the re-run are flaky (e.g. two parallel runs racing on a fixed /tmp path)
    and are dropped from scoring. Planted bugs: rows of 'truth'; real commits: rows of 'mine'."""
    done = set(merged(DFL))
    tree = make_tree(f"w{i}", CFG["commit"])
    jobs = [("truth", r) for r in merged("truth").values()] + [("mine", r) for r in real_set()]
    for stage, r in [j for j in jobs if j[1].get("failing") and f"{j[0]}:{j[1]['id']}" not in done][i::n]:
        key = f"{stage}:{r['id']}"
        try:
            if stage == "truth":
                apply_bug(tree, r)
            else:
                tree = make_tree(f"w{i}", r["commit"] + "^")
                apply_commit_src(tree, r)
            out = run_tests(tree, os.path.join(WORK, f"deflake_w{i}.json"), _rerun_targets(r["failing"]))
            if not out:
                raise RuntimeError("re-run produced no test outcomes")
            conf = _still_failing(r["failing"], out)
            append(DFL, i, {"id": key, "confirmed": conf, "flaky": sorted(set(r["failing"]) - set(conf))})
        except Exception as e:  # noqa: BLE001
            print(key, "ERROR", repr(e)[:300], flush=True)
        finally:
            reset(tree)


def deflake():
    jobs = [r for r in merged("truth").values() if r.get("failing")] + [r for r in real_set() if r.get("failing")]
    parallel("deflake", jobs)
    rows = merged(DFL)
    fl = sorted({t for r in rows.values() for t in r["flaky"]})
    log("deflake:", len(rows), "changes re-checked;", sum(bool(r["flaky"]) for r in rows.values()),
        "had flaky failures;", len(fl), "distinct flaky tests", fl[:10])


def _drop_new_tests(rows):
    """Rows scored before score_all excluded new tests: a failing test that the whole suite (retest_all) 'misses' was
    not in the suite before the change, so it is removed from every selector's misses and from the truth count."""
    out = []
    for r in rows:
        new = set(r["selectors"].get("retest_all", {}).get("missed", []))
        if not new:
            out.append(r)
            continue
        sels = {k: ({**v, "missed": [t for t in v["missed"] if t not in new]} if "missed" in v else v)
                for k, v in r["selectors"].items()}
        out.append({**r, "truth": r["truth"] - len(new), "selectors": sels,
                    "new_tests_excluded": r.get("new_tests_excluded", 0) + len(new)})
    return out


def _confirmed(rows, stage):
    """Score only confirmed failures: truth count and missed lists restricted to the tests that failed again."""
    rows = _drop_new_tests(rows)
    dfl = merged(DFL)
    if not dfl:
        return rows
    src = "truth" if stage == "select" else "mine"
    out = []
    for r in rows:
        d = dfl.get(f"{src}:{r['id']}")
        if d is None or not d["flaky"]:
            out.append(r)
            continue
        conf = set(d["confirmed"])
        sels = {k: ({**v, "missed": [t for t in v["missed"] if t in conf]} if "missed" in v else v)
                for k, v in r["selectors"].items()}
        out.append({**r, "truth": len(conf), "selectors": sels, "flaky_dropped": len(d["flaky"])})
    return out


# ---------------------------------------------------------------------------------------------------- repair

def rescore():
    """Re-record the coverage maps (base and each real commit's parent) with the current recorder and recompute the
    selection rows; the ground truth (truth, mine) is kept. Used for pygments after the recorder learned to record
    tests collected from data files (its first run left 1,504 such tests out of every map). Resumable: the old maps and
    rows are deleted once (marker file), then select and realeval continue where they stop."""
    marker = os.path.join(WORK, "rescore.started")
    if not os.path.exists(marker):
        for p in [os.path.join(WORK, "covmap.json"), *glob.glob(os.path.join(WORK, "real", "*", "covmap.json")),
                  *glob.glob(os.path.join(RES, "select.w*.jsonl")), *glob.glob(os.path.join(RES, "realeval.w*.jsonl"))]:
            os.remove(p)
        open(marker, "w").write(time.strftime("%F %T"))
        log("rescore: old coverage maps and selection rows removed")
    STAGES["select"]()
    STAGES["realeval"]()

def retestmon():
    """Recompute only pytest-testmon's rows (planted and real) with the current testmon_select, from the databases
    already recorded; every other selector's numbers are kept. (The first sqlglot run parsed testmon's console output,
    which came out empty at that project's verbosity.)"""
    base = baseline()
    plain = {k: t for k, (ok, t) in base.items()}
    for stage in ("select", "realeval"):
        files = sorted(glob.glob(os.path.join(RES, f"{stage}.w*.jsonl")))
        truth = merged("truth") if stage == "select" else {r["id"]: r for r in real_set()}
        bug_by_id = {b["id"]: b for b in bugs()} if stage == "select" else {}
        for p in files:
            rows = [json.loads(l) for l in open(p) if l.strip()]
            for row in rows:
                if stage == "realeval" and row["id"] not in truth:
                    continue
                if stage == "select":
                    tree, db = make_tree("w0", CFG["commit"]), testmon()
                    universe, pl = universe_of(covmap(), failing(base)), plain
                    apply_bug(tree, bug_by_id[row["id"]])
                    fails = truth_failing(truth[row["id"]], universe)
                else:
                    r, d = truth[row["id"]], os.path.join(WORK, "real", row["id"])
                    tree = make_tree("w0", r["commit"] + "^")
                    db = testmon(tree, os.path.join(d, "testmondata"))
                    b0 = jload(os.path.join(d, "base_outcomes.json"))
                    universe, pl = universe_of(jload(os.path.join(d, "covmap.json")), failing(b0)), \
                        {k: t for k, (ok, t) in b0.items()}
                    apply_commit_src(tree, r)
                    fails = r["failing"]
                try:
                    if not db:
                        row["selectors"].pop("testmon", None)
                        row["selectors"].pop("file_coverage", None)
                        continue
                    tot = sum(pl.get(n, 0) for n in universe) or 1e-9
                    share = lambda ss: round(sum(pl.get(n, 0) for n in ss) / tot, 4)
                    try:
                        s_ = set(testmon_select(tree, db)) & universe
                        row["selectors"]["testmon"] = {"selected": len(s_), "missed": SEL.missed(fails, s_),
                                                       "time_share": share(s_)}
                    except Exception as e:  # noqa: BLE001
                        row["selectors"]["testmon"] = {"error": repr(e)[:300]}
                    s_ = SEL.SELECTORS["file_coverage"](SEL.Change(tree, [CFG["pkg"]]), universe, testmon_db=db) \
                        & universe
                    row["selectors"]["file_coverage"] = {"selected": len(s_), "missed": SEL.missed(fails, s_),
                                                         "time_share": share(s_)}
                finally:
                    reset(tree)
            jdump_lines(rows, p)
        log("testmon rows recomputed:", stage)


def jdump_lines(rows, p):
    tmp = p + ".tmp"
    with open(tmp, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    os.replace(tmp, p)


# ---------------------------------------------------------------------------------------------------- TDAD baseline

TDAD_SKIP = {
    # TDAD's link_tests adds an edge from every test to every function of every file its test file imports; on sympy
    # (13,217 tests, 36,003 functions) its memory grew past 23 GB (WSL, 2026-10-26) and ~1.2 GB per 10 s in a re-check;
    # TDAD is run unmodified, so it is reported as not completing here
    "sympy": "did not complete: TDAD's test linking ran out of memory (over 23 GB)",
}


def tdad():
    """Add TDAD's selections (as published: cap 50; and uncapped) to the planted and real rows. TDAD is static and
    needs only the base code and the changed files, so no test is run here."""
    if REPO in TDAD_SKIP:
        log("TDAD skipped:", TDAD_SKIP[REPO])
        return
    import tdad_select as T
    base = baseline()
    plain = {k: t for k, (ok, t) in base.items()}
    for stage in ("select", "realeval"):
        info = merged("truth") if stage == "select" else merged("mine")
        for p in sorted(glob.glob(os.path.join(RES, f"{stage}.w*.jsonl"))):
            rows = [json.loads(l) for l in open(p) if l.strip()]
            for row in rows:
                if "tdad" in row["selectors"]:
                    continue
                if stage == "select":
                    b = info[row["id"]]
                    universe, pl = universe_of(covmap(), failing(base)), plain
                    tree, files, fails = make_tree("tdad", CFG["commit"]), [b["file"]], truth_failing(b, universe)
                else:
                    r, d = info[row["id"]], os.path.join(WORK, "real", row["id"])
                    tree, files, fails = make_tree("tdad", r["commit"] + "^"), r["src"], r["failing"]
                    b0 = jload(os.path.join(d, "base_outcomes.json")) or {}
                    cov = jload(os.path.join(d, "covmap.json")) or {}
                    universe, pl = universe_of(cov, failing(b0)), {k: t for k, (ok, t) in b0.items()}
                shutil.rmtree(os.path.join(tree, ".tdad"), ignore_errors=True) if stage == "realeval" else None
                T.index(tree)
                tot = sum(pl.get(n, 0) for n in universe) or 1e-9
                for name, cap in (("tdad", 50), ("tdad_nocap", None)):
                    s_ = T.expand(T.select(tree, files, cap), universe)
                    row["selectors"][name] = {"selected": len(s_), "missed": SEL.missed(fails, s_),
                                              "time_share": round(sum(pl.get(n, 0) for n in s_) / tot, 4)}
            jdump_lines(rows, p)
        log("TDAD rows added:", stage)


# ---------------------------------------------------------------------------------------------------- report

def report():
    lines = [f"# {REPO} ({CFG['commit'][:10]}; targets {' '.join(CFG['targets'])})", ""]
    for stage, title in (("select", "Planted bugs"), ("realeval", "Real commits")):
        rows = list(merged(stage).values())
        if stage == "realeval":
            ids = {r["id"] for r in real_set()}
            rows = [r for r in rows if r["id"] in ids]
        rows = _confirmed(rows, stage)
        if not rows:
            continue
        brk = [r for r in rows if r["truth"]]
        order = SELECTORS + ["namerts", "tdad", "tdad_nocap"]
        names = sorted({k for r in rows for k in r["selectors"]}, key=lambda k: order.index(k) if k in order else 99)
        nfl = sum(r.get("flaky_dropped", 0) for r in rows)
        nnew = sum(r.get("new_tests_excluded", 0) for r in rows)
        if nnew:
            lines += [f"({nnew} failing tests left out: they were created by the change, so no selector could pick "
                      "them)", ""]
        if stage == "select":
            hung = sum(1 for b in merged("truth").values() if b.get("timeout"))
            if hung:
                lines += [f"({hung} planted bugs left out: the test suite hung past the timeout on them)", ""]
        lines += [f"## {title}: {len(rows)} changes, {len(brk)} break tests ({sum(r['truth'] for r in brk)} failing tests)"
                  + (f"; {nfl} flaky failures dropped (passed when re-run)" if nfl else ""),
                  "", "| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |",
                  "|---|---|---|---|"]
        errs = {}
        for k in names:
            errs[k] = sum(1 for r in rows if "error" in r["selectors"].get(k, {}))
            have = [r for r in rows if k in r["selectors"] and "error" not in r["selectors"][k]]
            mb = [r for r in brk if k in r["selectors"] and "error" not in r["selectors"][k]]
            ts = [r["selectors"][k]["time_share"] for r in have]
            lines.append(f"| {k} | {sum(1 for r in mb if r['selectors'][k]['missed'])} of {len(mb)} | "
                         f"{sum(len(r['selectors'][k]['missed']) for r in mb)} | "
                         f"{100 * st.mean(ts):.1f}% ({100 * st.median(ts):.1f}%) |")
        for k, n in errs.items():
            if n:
                lines.append(f"\n{k}: could not run on {n} change(s) (e.g. the change breaks collection under it); "
                             "those changes are left out of its row")
        pv = [r for r in rows if "proviso" in r["selectors"]]
        tot = lambda r: r["selectors"]["proviso"]["selection_s"] + r["selectors"]["proviso"]["time_share"] * r["full_s"]
        lines += ["", f"End to end (plain s): full suite median {st.median(r['full_s'] for r in pv):.1f}; Proviso "
                  f"median {st.median(tot(r) for r in pv):.1f}, mean {st.mean(tot(r) for r in pv):.1f}; faster on "
                  f"{sum(tot(r) < r['full_s'] for r in pv)} of {len(pv)}; selection median "
                  f"{st.median(r['selectors']['proviso']['selection_s'] for r in pv):.2f} s", ""]
    if REPO in TDAD_SKIP:
        lines += [f"TDAD: {TDAD_SKIP[REPO]}", ""]
    open(os.path.join(RES, "report.md"), "w").write("\n".join(lines))
    print("\n".join(lines))


STAGES = {"prepare": prepare, "baseline": baseline, "covmap": covmap, "testmon": testmon, "nrinit": nrinit,
          "bugs": bugs, "truth": lambda: (baseline(), parallel("truth", bugs())),
          "select": lambda: (baseline(), covmap(), testmon(), nrinit(), drop_crash_rows(),
                             parallel("select", bugs(), NR_WORKERS)),
          "mine": lambda: parallel("mine", commits()), "realeval": lambda: parallel("realeval", real_set(), NR_WORKERS),
          "deflake": deflake, "report": report, "retestmon": retestmon, "tdad": tdad, "rescore": lambda: rescore()}
WORKER = {"truth": truth_worker, "select": select_worker, "mine": mine_worker, "realeval": realeval_worker,
          "deflake": deflake_worker}

if __name__ == "__main__":
    if sys.argv[1] == "report-all":
        for r in REPOS:
            use(r)
            if os.path.isdir(RES):
                report()
        sys.exit(0)
    use(sys.argv[1])
    if sys.argv[2] == "worker":
        WORKER[sys.argv[3]](int(sys.argv[4]), int(sys.argv[5]))
    else:
        for s in ([k for k in STAGES if k not in ("retestmon", "tdad", "rescore")] if sys.argv[2] == "all" else sys.argv[2:]):
            log("==", s)
            STAGES[s]()
