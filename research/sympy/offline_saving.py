"""Offline: what selection saves on each sympy task when the change is the reference fix.
For each task, the base tree gets the fix's source changes (not its tests); selection (dc_engine.impact.selection with
the task's coverage map) is compared with the task's subpackage tests, by count and by test time (per-test times from
the coverage run, i.e. with the profiler on; ratios are what matters).
Usage: python offline_saving.py EVAL_DIR OUT.json"""
import glob, json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src")); sys.path.insert(0, HERE)
from dc_engine import impact as I  # noqa: E402
from verify import WORK, G, istest  # noqa: E402
S = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad/offline-sel"
rows = []
for f in sorted(glob.glob(os.path.join(sys.argv[1], "tasks", "*.json"))):
    t = json.load(open(f))
    cov = json.load(open(os.path.join(sys.argv[1], "impact", t["id"], "covmap.json")))
    d = os.path.join(S, t["id"][:10])
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(f"{WORK}/{t['fix_commit'][:10]}/base", d, ignore=shutil.ignore_patterns("__pycache__"))
    g = lambda *a: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=d, capture_output=True)
    g("init", "-q"); g("add", "-A"); g("commit", "-qm", "b")
    shutil.copy(os.path.join(sys.argv[1], "impact", t["id"], "importstate_base.json"), os.path.join(d, ".dc-engine-tmp.json")) if False else None
    os.makedirs(os.path.join(d, ".dc-engine"), exist_ok=True)
    shutil.copy(os.path.join(sys.argv[1], "impact", t["id"], "importstate_base.json"), os.path.join(d, ".dc-engine", "importstate_base.json"))
    for p in [p for p in G("diff", "--name-only", t["commit"], t["fix_commit"]).stdout.split() if p.endswith(".py") and not istest(p)]:
        src = G("show", f"{t['fix_commit']}:{p}").stdout
        open(os.path.join(d, p), "w").write(src)
    sel, why = I.selection(d, cov, sys.executable)
    scope = [n for n in cov if not n.startswith("__") and any(n.startswith(s + "/") for s in t["subpackages"])]
    chosen = set(scope) if sel is None else set(sel) & set(scope)
    tsum = lambda ns: sum(cov[n].get("time", 0) for n in ns)
    r = {"task": t["id"], "scope_tests": len(scope), "selected": len(chosen), "scope_time": round(tsum(scope), 1),
         "selected_time": round(tsum(chosen), 1), "full": sel is None, "reason": why.get("reason", "")}
    rows.append(r)
    print(f"{t['id'][:40]:40s} tests {r['selected']:5d}/{r['scope_tests']:5d}  time {r['selected_time']:7.1f}/{r['scope_time']:7.1f}s "
          f"({r['selected_time'] / max(r['scope_time'], 1e-9):.0%}) {r['reason']}", flush=True)
    shutil.rmtree(d, ignore_errors=True)
json.dump(rows, open(sys.argv[2], "w"), indent=1)
tt = sum(r["scope_time"] for r in rows); st_ = sum(r["selected_time"] for r in rows)
print(f"TOTAL tests {sum(r['selected'] for r in rows)}/{sum(r['scope_tests'] for r in rows)}  time {st_:.0f}/{tt:.0f}s ({st_ / tt:.0%})")
