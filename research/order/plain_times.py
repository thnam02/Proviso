"""Per-test times without any tracer (the times an agent waits for), for the time-to-first-failure numbers.
planted bases: one plain run of each base tree (plugin cmp/plug/plaintime.py); real sqlglot commits: the plain run
of the changed tree recorded by prep_sqlglot_real.py (change.xml, run without testmon).
Writes results/plain_times.json {base tag or commit: {node id: seconds}}. Usage: python plain_times.py"""
import json, os, subprocess, sys, time
import xml.etree.ElementTree as ET
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import order as O  # noqa: E402
out_path = os.path.join(HERE, "results", "plain_times.json")
out = json.load(open(out_path)) if os.path.exists(out_path) else {}


def junit_times(xml):
    res = {}
    for c in ET.parse(xml).iter("testcase"):
        if not c.get("classname"):
            continue
        parts = c.get("classname").split(".")
        res[f"{'/'.join(parts[:-1])}.py::{parts[-1]}::{c.get('name')}"] = float(c.get("time") or 0)
    return res


for d in sorted(os.listdir(O.SQ)):
    p = os.path.join(O.SQ, d, "change.xml")
    if os.path.isfile(os.path.join(O.SQ, d, "proviso.json")) and os.path.exists(p):
        out[d] = junit_times(p)
for tag, tree, target in (("7f1cf60c88", "/home/claude/cmp/mut-7f1cf60c88", "tests"),
                          ("862fd55467", "/home/claude/cmp/mut-862fd55467", "tests"),
                          ("sympy-functions", os.path.join(O.S, "mut-sympy"), "sympy/functions")):
    if tag in out:
        continue
    subprocess.run(["git", "checkout", "-q", "--", "."], cwd=tree)
    tmp = os.path.join(O.S, f"plain_{tag}.json")
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": f"{tree}:/home/claude/cmp/plug", "PLAINTIME_OUT": tmp}
    t = time.time()
    subprocess.run(["python3", "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider", "-p", "plaintime",
                    "--continue-on-collection-errors", target], cwd=tree, env=env, capture_output=True, timeout=7200)
    out[tag] = json.load(open(tmp))
    print(tag, len(out[tag]), round(sum(out[tag].values()), 1), "s; wall", round(time.time() - t, 1), flush=True)
    json.dump(out, open(out_path, "w"))
json.dump(out, open(out_path, "w"))
print("ok", {k: len(v) for k, v in out.items() if not k[0].isdigit() or k in ("7f1cf60c88", "862fd55467")})
