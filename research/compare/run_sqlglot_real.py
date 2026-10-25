"""Score all selectors on the real sqlglot changes prepared by prep_sqlglot_real.py.
Usage: python run_sqlglot_real.py OUT.json"""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rts as SEL  # noqa: E402
from score import score_change  # noqa: E402
from prep_sqlglot_real import OUT, RIP  # noqa: E402

rows = []
for d in sorted(glob.glob(os.path.join(OUT, "*"))):
    tid = os.path.basename(d)
    if not os.path.isfile(os.path.join(d, "proviso.json")):
        continue
    cov = json.load(open(os.path.join(RIP, f"cov2_{tid}.json")))
    base = SEL.I._junit(os.path.join(d, "base.xml"))
    change = SEL.I._junit(os.path.join(d, "change.xml"))
    base_fail = {k for k, ok in base.items() if not ok}
    bad_files = {k for k in base_fail if "::" not in k}
    ok_at_base = lambda n: n not in base_fail and n.split("::", 1)[0] not in bad_files
    universe = {n for n in cov if not n.startswith("__") and ok_at_base(n)}
    truth = sorted(n for n, ok in change.items() if not ok and ok_at_base(n))
    ch = SEL.Change(os.path.join(d, "tree"), ["sqlglot"])
    pv = json.load(open(os.path.join(d, "proviso.json")))["selected"]
    ctx = {"testmon_db": os.path.join(d, "testmondata.base"),
           "testmon_selected": open(os.path.join(d, "testmon_selected.txt")).read().split(),
           "proviso_selected": pv, "roots": ("sqlglot", "tests")}
    for r in score_change(ch, universe, truth, cov, ctx):
        rows.append({"repo": "sqlglot", "dataset": "real", "change": tid, "files": len(ch.files), **r})
    print(tid, len(truth), "failing;", " ".join(f"{r['selector']}={r['selected']}{'!' if r['missed'] else ''}"
                                               for r in rows[-len(SEL.SELECTORS):]), flush=True)
json.dump(rows, open(sys.argv[1], "w"), indent=1)
