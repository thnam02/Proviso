"""Change-impact assets per task for the `impact` arm: covmap, base failures, probes, base outputs, replay runner.
Usage: python research/ripple/build_assets.py OUT_EVAL_DIR TASK_ID... (assets go to OUT_EVAL_DIR/impact/<task id>/)"""
import json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
W = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad/ripple"
COLLECTION_ERRORS = ["tests/dialects/test_bigquery.py", "tests/test_executor.py", "tests/test_optimizer.py"]

def build(out_dir, tid):
    k = tid[:10]
    dest = os.path.join(out_dir, "impact", tid)
    os.makedirs(dest, exist_ok=True)
    cov = json.load(open(os.path.join(W, f"cov2_{k}.json")))
    json.dump({n: {kk: vv for kk, vv in v.items() if kk != "ok"} for n, v in cov.items()},
              open(os.path.join(dest, "covmap.json"), "w"))
    fails = sorted(n for n, v in cov.items() if n != "__global__" and not v["ok"]) + COLLECTION_ERRORS
    json.dump(fails, open(os.path.join(dest, "base_failures.json"), "w"))
    shutil.copyfile(os.path.join(W, "trees", k, "probes.json"), os.path.join(dest, "probes.json"))
    shutil.copyfile(os.path.join(W, "trees", k, "base_out.json"), os.path.join(dest, "ripple_base.json"))
    shutil.copyfile(os.path.join(HERE, "replay.py"), os.path.join(dest, "replay.py"))
    return dest

if __name__ == "__main__":
    for t in sys.argv[2:]:
        print(build(sys.argv[1], t))
