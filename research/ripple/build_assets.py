"""Change-impact assets per task for the `impact` arm: covmap, base failures, probes, base outputs, replay runner.
Usage: python research/ripple/build_assets.py OUT_EVAL_DIR TASK_ID... (assets go to OUT_EVAL_DIR/impact/<task id>/)"""
import json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
W = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad/ripple"
COLLECTION_ERRORS = ["tests/dialects/test_bigquery.py", "tests/test_executor.py", "tests/test_optimizer.py"]

def build(out_dir, tid, python=None):
    k = tid[:10]
    dest = os.path.join(out_dir, "impact", tid)
    os.makedirs(dest, exist_ok=True)
    cov = json.load(open(os.path.join(W, f"cov2_{k}.json")))
    json.dump({n: {kk: vv for kk, vv in v.items() if kk != "ok"} for n, v in cov.items()},
              open(os.path.join(dest, "covmap.json"), "w"))
    fails = sorted(n for n, v in cov.items() if not n.startswith("__") and not v["ok"]) + COLLECTION_ERRORS
    json.dump(fails, open(os.path.join(dest, "base_failures.json"), "w"))
    shutil.copyfile(os.path.join(W, "trees", k, "probes.json"), os.path.join(dest, "probes.json"))
    shutil.copyfile(os.path.join(W, "trees", k, "base_out.json"), os.path.join(dest, "ripple_base.json"))
    shutil.copyfile(os.path.join(HERE, "replay.py"), os.path.join(dest, "replay.py"))
    if python:
        _import_state(os.path.join(W, "trees", k, "base"), cov, python, os.path.join(dest, "importstate_base.json"))
    return dest


def _import_state(base_tree, cov, python, out):
    """Precompute the base import-time snapshot (otherwise the first intercepted test run pays ~10 s for it). The
    cache is keyed by content, so a temporary repository holding the base tree produces the key the run will see."""
    import subprocess, tempfile
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
    from dc_engine import importstate
    from dc_engine.impact import _is_test_path
    files = sorted({f for v in cov.values() for f, _ in v["funcs"] if not _is_test_path(f)})  # as selection does
    tmp = tempfile.mkdtemp(prefix="assets-")
    try:
        for top in sorted({f.split("/", 1)[0] for f in files}):
            shutil.copytree(os.path.join(base_tree, top), os.path.join(tmp, top),
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        g = lambda *a: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=tmp, capture_output=True)
        g("init", "-q"); g("add", "-A"); g("commit", "-qm", "base")
        importstate.base_snapshot(tmp, files, python, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    # --python PATH: the interpreter of the run's virtualenv, for the import-time snapshot
    args = sys.argv[1:]
    py = None
    if "--python" in args:
        i = args.index("--python"); py = args[i + 1]; del args[i:i + 2]
    for t in args[1:]:
        print(build(args[0], t, py))
