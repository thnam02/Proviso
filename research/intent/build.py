"""Cases for the intent check: real sqlglot fixes (intended changes only) and the same fixes with one planted bug
in a file the fix touched (an unintended side effect, the way an agent's fix can go slightly wrong).

Per task (a real commit; base = its parent):
  B   base tree;  FT  base + the fix's source + the fix's tests
  probes  inputs of the base tests and of the fix's new tests (research/ripple/replay.py), each run in its dialect
          and in every dialect inheriting from it
  fix case     behaviour of FT vs B: import-time values that changed, outputs that changed
  bug cases    up to N_BUGS bugs (comparison/boolean flips, deleted table entries, flipped flags) in the files the
               fix changed; behaviour vs B, whether it differs observably from the fix alone (ground truth: some
               output or import-time value differs from FT's), and whether the tests (the fix's suite) catch it
Writes data/<task>.json. Usage: python build.py N_TASKS N_BUGS SEED"""
import glob, json, os, random, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "research", "ripple"))
sys.path.insert(0, os.path.join(ROOT, "src"))
import behaviour as BH  # noqa: E402
import mutants as M  # noqa: E402
import replay as R  # noqa: E402
from dc_engine import impact as I  # noqa: E402

SQ = "/home/claude/cmp/sq"
RIP = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad/ripple"
SRC = "/home/claude/sources/sqlglot"
W = "/home/claude/cmp/intent"
DATA = os.path.join(HERE, "data")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True).stdout


def task_prompt(tid):
    for p in glob.glob(os.path.join(ROOT, "eval", "tasks*", f"{tid}*.json")):
        return json.load(open(p))["prompt"]
    return git(SRC, "log", "-1", "--format=%s%n%n%b", tid).strip()


def suite(tree, xml):
    if os.path.exists(xml):
        os.remove(xml)
    subprocess.run(["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no",
                    "--continue-on-collection-errors", f"--junitxml={xml}", "tests"], cwd=tree,
                   env=BH._env(tree), capture_output=True, timeout=1800)
    return {n for n, ok in I._junit(xml).items() if not ok}


def build(tid, n_bugs, rnd):
    out_path = os.path.join(DATA, f"{tid}.json")
    if os.path.exists(out_path):
        return
    d = os.path.join(W, tid)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    B, FT = os.path.join(d, "base"), os.path.join(d, "fix")
    ign = shutil.ignore_patterns("__pycache__", ".testmondata", ".pytest_cache", ".dc-engine")
    shutil.copytree(os.path.join(SQ, tid, "tree"), FT, ignore=ign)       # base + fix source (working tree)
    shutil.copytree(FT, B)
    git(B, "checkout", "-q", "--", "."); git(B, "clean", "-fdq")
    fix = git(SRC, "rev-parse", tid).strip()
    for p in git(SRC, "diff", "--name-only", f"{fix}^", fix, "--", "tests").split():   # the fix's tests
        blob = subprocess.run(["git", "show", f"{fix}:{p}"], cwd=SRC, capture_output=True).stdout
        if blob:
            os.makedirs(os.path.dirname(os.path.join(FT, p)), exist_ok=True)
            open(os.path.join(FT, p), "wb").write(blob)
    src_files = [l for l in git(FT, "diff", "--name-only", "HEAD", "--", "sqlglot").split() if l.endswith(".py")]
    # probes: base inputs + the fix's new inputs
    base_probes = json.load(open(os.path.join(RIP, "trees", tid, "probes.json")))
    have = {(p[0], p[2]) for p in base_probes if p[0] == p[1]}
    new_corpus = [c for c in R.corpus(FT) if tuple(c) not in have]
    probes = base_probes + R.probes(new_corpus, R.ripple(FT))
    pp = os.path.join(d, "probes.json")
    json.dump(probes, open(pp, "w"))
    base_out = BH.replay(B, pp, os.path.join(d, "base_out.json"))
    fix_out = BH.replay(FT, pp, os.path.join(d, "fix_out.json"))
    snap_b, snap_f = BH.snapshot(B), BH.snapshot(FT)
    fix_fail = suite(FT, os.path.join(d, "fix.xml"))
    cases = [{"task": tid, "variant": "fix", "label": "intended", "prompt": task_prompt(tid),
              "code_diff": git(FT, "diff", "HEAD", "--", "sqlglot"),
              "import_changes": BH.import_changes(B, FT, snap_b, snap_f, d),
              "output_changes": BH.output_changes(base_out, fix_out, probes), "new_probes": len(probes) - len(base_probes)}]
    cands = M.candidates(FT, "sqlglot")
    pool = [(k, c) for k in ("function", "class", "module") for c in cands[k] if c[0] in src_files]
    rnd.shuffle(pool)
    pristine = {f: open(os.path.join(FT, f), encoding="utf-8").read() for f in src_files}
    for kind, (rel, ln, op) in pool:
        if sum(c["variant"] == "bug" for c in cases) >= n_bugs:
            break
        text = M.apply(FT, rel, ln, op)
        try:
            out = BH.replay(FT, pp, os.path.join(d, "bug_out.json"))
            snap = BH.snapshot(FT)
            if snap is None:  # the bug breaks importing the package: trivially visible, not interesting here
                continue
            vs_fix_outputs = sum(1 for k in set(out) | set(fix_out) if out.get(k) != fix_out.get(k))
            vs_fix_imports = BH.importstate.diff(snap_f, snap)["changed"]
            observable = bool(vs_fix_outputs or vs_fix_imports)
            fails = suite(FT, os.path.join(d, "bug.xml")) - fix_fail
            cases.append({"task": tid, "variant": "bug", "label": "unintended" if observable else "no_effect",
                          "prompt": cases[0]["prompt"], "bug": {"kind": kind, "file": rel, "line": ln, "op": op,
                                                                 "code": text},
                          "code_diff": git(FT, "diff", "HEAD", "--", "sqlglot"),
                          "import_changes": BH.import_changes(B, FT, snap_b, snap, d),
                          "output_changes": BH.output_changes(base_out, out, probes),
                          "differs_from_fix": {"outputs": vs_fix_outputs, "imports": len(vs_fix_imports)},
                          "caught_by_tests": bool(fails), "new_failures": sorted(fails)[:20]})
            print(tid, kind, rel, ln, "observable" if observable else "no effect",
                  "caught" if fails else "silent", flush=True)
        finally:
            open(os.path.join(FT, rel), "w", encoding="utf-8").write(pristine[rel])
    json.dump(cases, open(out_path, "w"), indent=1)
    shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    n_tasks, n_bugs, seed = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    os.makedirs(DATA, exist_ok=True)
    rnd = random.Random(seed)
    tids = sorted(os.path.basename(p) for p in glob.glob(os.path.join(SQ, "*")) if os.path.isfile(os.path.join(p, "proviso.json")))
    for tid in rnd.sample(tids, min(n_tasks, len(tids))):
        try:
            build(tid, n_bugs, random.Random(f"{seed}-{tid}"))
        except Exception as e:  # noqa: BLE001
            print(tid, "ERROR", repr(e)[:300], flush=True)
