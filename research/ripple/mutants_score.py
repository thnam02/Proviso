"""Re-score planted-bug results: module load errors count as caught if any selected test is in that module;
the three modules that already fail at base (pytz not installed) are excluded."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
import mutants as M
from dc_engine import impact as I
BASE_BAD = {"tests/dialects/test_bigquery.py", "tests/test_executor.py", "tests/test_optimizer.py"}
out = []
for prefix, seed, path in (("7f1cf60c88", 1, "mutants_7f1c.json"), ("862fd55467", 2, "mutants_862f.json")):
    work = os.path.join(M.W, f"mut-{prefix}-{seed}")
    cov = json.load(open(os.path.join(M.W, f"cov2_{prefix}.json")))
    for r in json.load(open(os.path.join(HERE, path))):
        subprocess.run(["git", "checkout", "-q", "--", "."], cwd=work)
        M.apply(work, r["file"], r["line"], r["op"])
        sel, why = I.selection(work, cov)
        selected = (set(cov) - {"__global__"}) if sel is None else set(sel)
        real_missed, mod_missed, mod_caught = [], [], []
        for n in r["missed"]:
            if n.startswith(".py::::"):
                mod = n[len(".py::::"):].replace(".", "/") + ".py"
                if mod in BASE_BAD:
                    continue
                (mod_caught if any(s.startswith(mod) for s in selected) else mod_missed).append(mod)
            elif n not in selected:
                real_missed.append(n)
        killed = r["failing"] - sum(1 for n in r["missed"] if n.startswith(".py::::") and
                                    n[len(".py::::"):].replace(".", "/") + ".py" in BASE_BAD) > 0
        out.append({**r, "commit": prefix, "killed": killed, "selected": len(selected),
                    "real_missed": real_missed, "module_missed": mod_missed, "module_caught": mod_caught,
                    "safe": not real_missed and not mod_missed})
    subprocess.run(["git", "checkout", "-q", "--", "."], cwd=work)
json.dump(out, open(os.path.join(HERE, "mutants_scored.json"), "w"), indent=1)
import collections
for kind in ("function", "class", "module"):
    rs = [x for x in out if x["kind"] == kind]
    k = [x for x in rs if x["killed"]]
    print(f"{kind:9s} planted {len(rs):2d}  caught by full suite {len(k):2d}  selection safe on {sum(x['safe'] for x in k)}/{len(k)}"
          f"  median selected {sorted(x['selected'] for x in k)[len(k)//2] if k else '-'}")
bad = [x for x in out if x["killed"] and not x["safe"]]
for x in bad: print("MISS", x["kind"], x["file"], x["line"], x["code"][:70], x["real_missed"][:3], x["module_missed"][:3])
