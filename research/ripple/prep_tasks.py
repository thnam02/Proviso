"""Trees, replay probes and base outputs for tasks in a task dir (for impact assets). Usage: prep_tasks.py TASK_DIR"""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import replay as R
from feasibility import tree, W
for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.json"))):
    t = json.load(open(f)); td = os.path.join(W, "trees", t["id"][:10])
    base = tree(t["commit"], os.path.join(td, "base"))
    pp, bo = os.path.join(td, "probes.json"), os.path.join(td, "base_out.json")
    if not os.path.isfile(bo):
        json.dump(R.probes(R.corpus(base), R.ripple(base)), open(pp, "w"))
        R.run(base, pp, bo)
    print(t["id"][:10], "ready", flush=True)
