"""Third-repository study: SQLAlchemy (never used while developing Proviso), same protocol as research/compare.

Stages (each resumable; results in research/sqla/results/, scratch in $PROVISO_WORK, default ~/proviso-work/sqla):
  prepare   clone SQLAlchemy, base tree at COMMIT
  baseline  plain run of the targets at the base: outcomes and per-test times (no tracing)
  covmap    Proviso's coverage map at the base (research/ripple/covplugin_mon.py)
  testmon   pytest-testmon database at the base
  nrinit    NameRTS initialised at the base
  bugs      planted single-line bugs (function / class / module) in lib/sqlalchemy/{sql,engine}, sampled per kind
  truth     ground truth per bug: the targets run on the bugged tree (parallel, one tree per worker)
  select    every selector per bug, plus Proviso's warm selection time (parallel)
  mine      real commits: each commit's source changes applied to its parent, parent's tests run; which break tests
  realeval  every selector on the mined commits (per commit: its own coverage map, testmon database, NameRTS init)
  report    tables (results/report.md)
Usage: python pipeline.py all | STAGE [STAGE ...]        (env: PROVISO_WORK, PROVISO_WORKERS, SQLA_SMOKE=1)"""
from __future__ import annotations

import glob
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
import mutants as M  # noqa: E402
import rts as SEL  # noqa: E402

SMOKE = os.environ.get("SQLA_SMOKE") == "1"  # a few bugs and commits, to test the pipeline
REPO_URL = "https://github.com/sqlalchemy/sqlalchemy.git"
COMMIT = "10f4d1e2d"
PKG = "lib/sqlalchemy"
TARGETS = ["test/base", "test/sql"]
MUTATE = ["sql", "engine"]
PER_KIND = {"function": 2, "class": 2, "module": 2} if SMOKE else {"function": 40, "class": 30, "module": 25}
SEED = 2027
SCAN_COMMITS = 6 if SMOKE else 400        # recent commits touching the mutated packages, scanned for test breaks
REAL_NONBREAKING = 2 if SMOKE else 40     # non-breaking real commits also evaluated (selection size)
WORK = os.environ.get("PROVISO_WORK", os.path.expanduser("~/proviso-work/sqla"))
WORKERS = int(os.environ.get("PROVISO_WORKERS", max(1, (os.cpu_count() or 2) - 1)))
RES = os.path.join(HERE, "results" + ("_smoke" if SMOKE else ""))
PY = sys.executable
PYTEST = ["-p", "no:randomly", "--maxfail=1000000", "--tb=no", "-q", "--continue-on-collection-errors"]
SELECTORS = ["retest_all", "name_match", "static_imports", "file_coverage", "testmon", "func_only", "func_file", "proviso"]
os.makedirs(WORK, exist_ok=True)
os.makedirs(RES, exist_ok=True)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def git(cwd, *a, check=False):
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr[-400:]}")
    return r.stdout


def env(tree, extra_path=(), **kw):
    e = {"PATH": os.path.dirname(PY) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
         "HOME": os.environ.get("HOME", "/tmp"), "PYTHONDONTWRITEBYTECODE": "1", "PROVISO_PY": PY,
         "PYTHONPATH": os.pathsep.join([os.path.join(tree, "lib"), *extra_path,
                                        *[x for x in os.environ.get("PROVISO_EXTRA_PATH", "").split(os.pathsep) if x]])}
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
        subprocess.run(["git", "clone", "-q", REPO_URL, d], check=True)
    return d


def make_tree(name, commit):
    """A clone of the source repository at `commit` (shared objects: cheap)."""
    d = os.path.join(WORK, "trees", name)
    if not os.path.isdir(os.path.join(d, ".git")):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", src_repo(), d], check=True)
    git(d, "checkout", "-q", "-f", commit, check=True)
    git(d, "clean", "-fdqx", "-e", ".dc-engine")
    return d


def reset(tree):
    git(tree, "checkout", "-q", "--", ".")
    git(tree, "clean", "-fdq", "-e", ".dc-engine")


def run_tests(tree, out, plugin="outcomes", targets=None, extra=(), extra_env=None, timeout=7200):
    """Run the targets with one of our plugins; returns the plugin's JSON."""
    e = env(tree, [os.path.join(HERE, "plug"), os.path.join(ROOT, "research", "ripple")], **(extra_env or {}))
    e["OUTCOMES_OUT"] = e["COVMAP_OUT"] = out
    if os.path.exists(out):
        os.remove(out)
    subprocess.run([PY, "-m", "pytest", "-p", "no:cacheprovider", "-p", plugin, *PYTEST, *extra,
                    *(targets or TARGETS)], cwd=tree, env=e, capture_output=True, timeout=timeout)
    return jload(out, {})


def failing(outcomes):
    return {n for n, (ok, _) in outcomes.items() if not ok}


def ok_filter(base_fail):
    bad = {k for k in base_fail if "::" not in k}
    return lambda n: n not in base_fail and n.split("::", 1)[0] not in bad


# ---------------------------------------------------------------------------------------------------- base assets

def prepare():
    tree = make_tree("base", COMMIT)
    log("base tree", tree, git(tree, "log", "-1", "--format=%h %cd").strip())


def baseline(tree=None, out=None):
    tree = tree or make_tree("base", COMMIT)
    out = out or os.path.join(RES, "base_outcomes.json")
    if not jload(out):
        t = time.time()
        r = run_tests(tree, os.path.join(WORK, "tmp_outcomes.json") if out.startswith(RES) else out + ".run")
        jdump(r, out)
        log("baseline", len(r), "tests,", len(failing(r)), "failing,", round(time.time() - t), "s")
    return jload(out)


def covmap(tree=None, out=None):
    tree = tree or make_tree("base", COMMIT)
    out = out or os.path.join(WORK, "covmap.json")
    if not jload(out):
        t = time.time()
        run_tests(tree, out, plugin="covplugin_mon", extra_env={"COVMAP_PKG": PKG})
        log("covmap", len(jload(out, {})), "entries,", round(time.time() - t), "s")
    return jload(out)


def testmon(tree=None, db=None):
    tree = tree or make_tree("base", COMMIT)
    db = db or os.path.join(WORK, "testmondata.base")
    if not os.path.exists(db):
        reset(tree)
        e = env(tree)
        t = time.time()
        # testmon needs the cache provider (do not pass -p no:cacheprovider)
        subprocess.run([PY, "-m", "pytest", "--testmon", *PYTEST, *TARGETS], cwd=tree, env=e, capture_output=True,
                       timeout=7200)
        shutil.move(os.path.join(tree, ".testmondata"), db)
        shutil.rmtree(os.path.join(tree, ".pytest_cache"), ignore_errors=True)
        log("testmon db", round(time.time() - t), "s")
    return db


def testmon_select(tree, db):
    shutil.copy(db, os.path.join(tree, ".testmondata"))
    r = subprocess.run([PY, "-m", "pytest", "--co", "--testmon", "-qq", "-p", "no:randomly",
                        "--continue-on-collection-errors", *TARGETS], cwd=tree, env=env(tree), capture_output=True,
                       text=True, timeout=3600)
    os.remove(os.path.join(tree, ".testmondata"))
    shutil.rmtree(os.path.join(tree, ".pytest_cache"), ignore_errors=True)
    head = next((l for l in r.stdout.splitlines() if l.startswith("testmon:")), "")
    if "deactivated" in head:
        raise RuntimeError("testmon selection deactivated: " + head)
    return [l for l in r.stdout.splitlines() if "::" in l and not l.startswith(("ERROR", "FAILED"))]


NR_ENV = {"NAMERTS_HOME": os.environ.get("NAMERTS_HOME", os.path.join(WORK, "NameRTS")),
          "NAMERTS_BIN": os.path.join(HERE, "nrts-bin"), "NAMERTS_DEPS": os.environ.get("NAMERTS_DEPS", ""),
          "NAMERTS_LOGS": os.path.join(WORK, "nr-logs"), "NAMERTS_SCOPE": ",".join(TARGETS), "NAMERTS_WORKERS": "2",
          "NAMERTS_TEST_DIRS": "test"}


def namerts(action, tree, cache):
    e = {**os.environ, **NR_ENV, "PROVISO_PY": PY, "PATH": os.path.dirname(PY) + os.pathsep + os.environ.get("PATH", ""),
         "NAMERTS_EXTRA_PATH": os.path.join(tree, "lib")}
    r = subprocess.run([PY, os.path.join(ROOT, "research", "compare", "namerts_driver.py"), action, tree, cache,
                        "sqlalchemy"], capture_output=True, text=True, env=e, timeout=14400)
    if action == "select":
        for line in r.stdout.splitlines():
            if line.startswith("NAMERTS_SELECTED "):
                return json.loads(line[len("NAMERTS_SELECTED "):])
        raise RuntimeError("NameRTS selection failed: " + (r.stdout + r.stderr)[-600:])
    if not os.path.isfile(os.path.join(cache, "nbdp_cache.json")):
        raise RuntimeError("NameRTS init failed: " + (r.stdout + r.stderr)[-600:])


def nr_available():
    return os.path.isdir(NR_ENV["NAMERTS_HOME"])


def nrinit(tree=None, cache=None):
    if not nr_available():
        log("NameRTS not installed (run_all.sh installs it); skipped")
        return None
    tree = tree or make_tree("nr-base", COMMIT)
    cache = cache or os.path.join(WORK, "nr-cache")
    if not os.path.isfile(os.path.join(cache, "nbdp_cache.json")):
        t = time.time()
        namerts("init", tree, cache)
        log("NameRTS init", round(time.time() - t), "s")
    return cache


# ---------------------------------------------------------------------------------------------------- planted bugs

def _string_lines(path):
    """Lines inside multi-line string constants (docstrings): a flip there changes no behaviour."""
    import ast
    try:
        mod = ast.parse(open(path, encoding="utf-8").read())
    except SyntaxError:
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
    tree = make_tree("base", COMMIT)
    cands = M.candidates(tree, PKG, MUTATE)
    skip = {}
    rnd = random.Random(SEED)
    chosen = []
    for kind, n in PER_KIND.items():
        pool = []
        for rel, ln, op in cands[kind]:
            if "/testing/" in rel:
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


def parallel(stage, items):
    """Run `python pipeline.py worker STAGE i n` for i in 0..n-1; each handles items[i::n] in its own tree."""
    n = max(1, min(WORKERS, len(items)))
    procs = [subprocess.Popen([PY, os.path.abspath(__file__), "worker", stage, str(i), str(n)],
                              stdout=open(os.path.join(WORK, f"{stage}.w{i}.log"), "a"), stderr=subprocess.STDOUT)
             for i in range(n)]
    for p in procs:
        p.wait()
    log(stage, "workers done; logs in", WORK)


def merged(stage):
    rows = {}
    for p in glob.glob(os.path.join(RES, f"{stage}.w*.jsonl")):
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
    todo = [b for b in bugs()[i::n] if b["id"] not in done]
    tree = make_tree(f"w{i}", COMMIT)
    base_fail = failing(baseline())
    ok = ok_filter(base_fail)
    for b in todo:
        try:
            code = apply_bug(tree, b)
            t = time.time()
            r = run_tests(tree, os.path.join(WORK, f"truth_w{i}.json"))
            fails = sorted(x for x in failing(r) if ok(x))
            append("truth", i, {**b, "code": code, "failing": fails, "n_tests": len(r), "secs": round(time.time() - t, 1)})
            print(b["id"], len(fails), "failing", flush=True)
        finally:
            reset(tree)


# ---------------------------------------------------------------------------------------------------- selection

def universe_of(cov, base_fail):
    ok = ok_filter(base_fail)
    return {n for n in cov if n != "__global__" and ok(n)}


def score_all(tree, cov, universe, truth, plain, testmon_db, nr_cache, nr_tree=None):
    """Rows for every selector on the change in `tree` (working tree vs HEAD); times: plain seconds."""
    ch = SEL.Change(tree, [PKG])
    T = lambda ns: sum(plain.get(n, 0) for n in ns)
    tot = T(universe) or 1e-9
    ctx = {"testmon_db": testmon_db, "roots": (PKG, "test"), "top": "sqlalchemy"}
    rows = {}
    ctx["testmon_selected"] = testmon_select(tree, testmon_db)
    I.selection(tree, cov, PY)                         # warm the per-commit caches (as after a session's first run)
    t = time.time()
    psel, why = I.selection(tree, cov, PY)
    sel_s = time.time() - t
    ctx["proviso_selected"] = psel
    for name in SELECTORS:
        s = SEL.SELECTORS[name](ch, universe, cov=cov, **ctx)
        rows[name] = {"selected": len(s & universe), "time_share": round(T(s & universe) / tot, 4),
                      "missed": SEL.missed(truth, s)}
    rows["proviso"]["selection_s"] = round(sel_s, 2)
    rows["proviso"]["reason"] = why.get("reason")
    if nr_cache:
        nt = nr_tree
        reset(nt)
        # the same change in NameRTS's own tree (initialised at the same commit)
        diff = subprocess.run(["git", "diff", "HEAD"], cwd=tree, capture_output=True).stdout
        if diff:
            subprocess.run(["git", "apply", "--whitespace=nowarn"], cwd=nt, input=diff, check=True)
        files = set(namerts("select", nt, nr_cache))
        s = {n for n in universe if n.split("::", 1)[0] in files}
        rows["namerts"] = {"selected": len(s), "time_share": round(T(s) / tot, 4), "missed": SEL.missed(truth, s)}
        reset(nt)
    return {"universe": len(universe), "full_s": round(tot, 2), "truth": len(truth), "selectors": rows}


def select_worker(i, n):
    done = set(merged("select"))
    truth = merged("truth")
    todo = [b for b in bugs()[i::n] if b["id"] not in done and b["id"] in truth]
    tree = make_tree(f"w{i}", COMMIT)
    nr_cache = os.path.join(WORK, "nr-cache") if os.path.isfile(os.path.join(WORK, "nr-cache", "nbdp_cache.json")) else None
    nr_tree = make_tree(f"nr-w{i}", COMMIT) if nr_cache else None
    cov = covmap()
    base = baseline()
    plain = {n: t for n, (ok, t) in base.items()}
    universe = universe_of(cov, failing(base))
    db = testmon()
    for b in todo:
        try:
            apply_bug(tree, b)
            r = score_all(tree, cov, universe, truth[b["id"]]["failing"], plain, db, nr_cache, nr_tree)
            append("select", i, {"id": b["id"], "kind": b["kind"], **r})
            print(b["id"], {k: (v["selected"], len(v["missed"])) for k, v in r["selectors"].items()}, flush=True)
        finally:
            reset(tree)


# ---------------------------------------------------------------------------------------------------- real commits

def commits():
    out = os.path.join(RES, "commits.json")
    if jload(out):
        return jload(out)
    s = src_repo()
    log_ = git(s, "log", "--first-parent", "--no-merges", f"-n{SCAN_COMMITS * 3}", "--format=%H", COMMIT, "--",
               *[f"{PKG}/{d}" for d in MUTATE])
    cs = []
    for h in log_.split():
        files = git(s, "diff", "--name-only", f"{h}^", h).split()
        src = [f for f in files if f.startswith(PKG + "/") and f.endswith(".py") and "/testing/" not in f]
        if src and len(src) <= 15:
            cs.append({"id": h[:10], "commit": h, "src": src})
        if len(cs) >= SCAN_COMMITS:
            break
    jdump(cs, out)
    log("commits to scan", len(cs))
    return cs


def apply_commit_src(tree, c):
    """The commit's source changes (not its test changes) on top of its parent."""
    for f in c["src"]:
        blob = subprocess.run(["git", "show", f"{c['commit']}:{f}"], cwd=tree, capture_output=True)
        p = os.path.join(tree, f)
        if blob.returncode:          # deleted by the commit
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
            fails = sorted(x for x in failing(ch) if ok(x))
            append("mine", i, {"id": c["id"], "commit": c["commit"], "src": c["src"], "failing": fails,
                               "base_failing": sorted(failing(base)), "n_tests": len(base)})
            print(c["id"], len(fails), "failing", flush=True)
        finally:
            reset(tree)


def real_set():
    m = sorted(merged("mine").values(), key=lambda r: r["id"])
    breaking = [r for r in m if r["failing"]]
    rnd = random.Random(SEED)
    rest = [r for r in m if not r["failing"]]
    rnd.shuffle(rest)
    return breaking + rest[:REAL_NONBREAKING]


def realeval_worker(i, n):
    done = set(merged("realeval"))
    for r in [r for r in real_set()[i::n] if r["id"] not in done]:
        parent = r["commit"] + "^"
        d = os.path.join(WORK, "real", r["id"])
        os.makedirs(d, exist_ok=True)
        tree = make_tree(f"w{i}", parent)
        try:
            base = baseline(tree, os.path.join(d, "base_outcomes.json"))
            cov = covmap(tree, os.path.join(d, "covmap.json"))
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
            print(r["id"], {k: (v["selected"], len(v["missed"])) for k, v in res["selectors"].items()}, flush=True)
        except Exception as e:  # noqa: BLE001
            print(r["id"], "ERROR", repr(e)[:400], flush=True)
        finally:
            reset(tree)


# ---------------------------------------------------------------------------------------------------- report

def report():
    lines = [f"# SQLAlchemy ({COMMIT}; targets {' '.join(TARGETS)})", ""]
    for stage, title in (("select", "Planted bugs"), ("realeval", "Real commits")):
        rows = list(merged(stage).values())
        if not rows:
            continue
        brk = [r for r in rows if r["truth"]]
        names = sorted({k for r in rows for k in r["selectors"]}, key=lambda k: (SELECTORS + ["namerts"]).index(k))
        lines += [f"## {title}: {len(rows)} changes, {len(brk)} break tests ({sum(r['truth'] for r in brk)} failing tests)",
                  "", "| selector | changes with a missed failure | failing tests missed | test time selected, mean (median) |",
                  "|---|---|---|---|"]
        for k in names:
            have = [r for r in rows if k in r["selectors"]]
            mb = [r for r in brk if k in r["selectors"]]
            ts = [r["selectors"][k]["time_share"] for r in have]
            lines.append(f"| {k} | {sum(1 for r in mb if r['selectors'][k]['missed'])} of {len(mb)} | "
                         f"{sum(len(r['selectors'][k]['missed']) for r in mb)} | "
                         f"{100 * st.mean(ts):.1f}% ({100 * st.median(ts):.1f}%) |")
        pv = [r for r in rows if "proviso" in r["selectors"]]
        tot = lambda r: r["selectors"]["proviso"]["selection_s"] + r["selectors"]["proviso"]["time_share"] * r["full_s"]
        lines += ["", f"End to end (plain s): full suite median {st.median(r['full_s'] for r in pv):.1f}; Proviso "
                  f"(selection + selected tests) median {st.median(tot(r) for r in pv):.1f}, mean "
                  f"{st.mean(tot(r) for r in pv):.1f}; faster on {sum(tot(r) < r['full_s'] for r in pv)} of {len(pv)}; "
                  f"selection median {st.median(r['selectors']['proviso']['selection_s'] for r in pv):.2f} s", ""]
    open(os.path.join(RES, "report.md"), "w").write("\n".join(lines))
    print("\n".join(lines))


STAGES = {"prepare": prepare, "baseline": baseline, "covmap": covmap, "testmon": testmon, "nrinit": nrinit,
          "bugs": bugs, "truth": lambda: parallel("truth", bugs()), "select": lambda: parallel("select", bugs()),
          "mine": lambda: parallel("mine", commits()), "realeval": lambda: parallel("realeval", real_set()),
          "report": report}
WORKER = {"truth": truth_worker, "select": select_worker, "mine": mine_worker, "realeval": realeval_worker}

if __name__ == "__main__":
    if sys.argv[1] == "worker":
        WORKER[sys.argv[2]](int(sys.argv[3]), int(sys.argv[4]))
    else:
        for s in (list(STAGES) if sys.argv[1] == "all" else sys.argv[1:]):
            log("==", s)
            STAGES[s]()
