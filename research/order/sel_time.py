"""Wall time of Proviso's selection (dc_engine.impact.selection) on the real sqlglot commits.
  cold   first selection on the base commit: also builds the base import-time snapshot and the base source indexes
         (once per agent session, like the coverage map)
  warm   a later selection in the same session (base caches present): the cost paid on every test run
Each commit's selection is checked to be identical cold and warm, and against the stored selection (proviso.json).
Usage: python sel_time.py OUT.json"""
import glob, json, os, shutil, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import order as O  # noqa: E402
rows = []
for d in sorted(glob.glob(os.path.join(O.SQ, "*"))):
    tid = os.path.basename(d)
    if not os.path.isfile(os.path.join(d, "proviso.json")):
        continue
    tree = os.path.join(d, "tree")
    cov = json.load(open(os.path.join(O.S, "ripple", f"cov2_{tid}.json")))
    shutil.rmtree(os.path.join(tree, O.SEL.I.STATE_DIR), ignore_errors=True)
    t = time.time(); s1, why = O.SEL.I.selection(tree, cov, "python3"); cold = time.time() - t
    t = time.time(); s2, _ = O.SEL.I.selection(tree, cov, "python3"); warm = time.time() - t
    stored = json.load(open(os.path.join(d, "proviso.json")))["selected"]
    rows.append({"change": tid, "cold": round(cold, 2), "warm": round(warm, 2), "full": s1 is None,
                 "same_cold_warm": s1 == s2, "same_as_stored": (s1 or None) == (stored or None) or set(s1 or []) == set(stored or []),
                 "import_state": "import_state_n" in why})
    print(tid, rows[-1], flush=True)
    json.dump(rows, open(sys.argv[1], "w"), indent=1)
