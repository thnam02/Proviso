"""Overhead of Proviso, and the sys.monitoring recorder.

For a base tree: wall time of the test suite (a) plain, (b) recording the coverage map with covplugin.py
(sys.setprofile), (c) recording it with covplugin_mon.py (sys.monitoring); whether (b) and (c) give the same map
(funcs, classes, always per test; __global__); the time of the import-time snapshot (importstate) and of one
selection (dc_engine.impact.selection) on a sample of changes.
Usage: python overhead.py sqlglot TREE PKG_TARGETS... -- OUT.json
       (env COVMAP_PKG / COVMAP_BEFORE_TEST as for the recorders)"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RIPPLE = os.path.join(ROOT, "research", "ripple")
S = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad"


def run(tree, targets, plugin, out, extra_env):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": f"{tree}:{RIPPLE}", "HOME": "/tmp",
           "PYTHONDONTWRITEBYTECODE": "1", **extra_env}
    args = ["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no", "--continue-on-collection-errors"]
    if plugin:
        env["COVMAP_OUT"] = out
        args += ["-p", plugin]
    t = time.time()
    subprocess.run(args + targets, cwd=tree, env=env, capture_output=True, timeout=14400)
    return time.time() - t


def same(a, b):
    diff = {"funcs": 0, "classes": 0, "always": 0, "missing": 0}
    for n in set(a) | set(b):
        if n not in a or n not in b:
            diff["missing"] += 1
            continue
        for k in ("funcs", "classes", "always"):
            if k in a[n] and sorted(map(tuple, a[n][k]) if k == "funcs" else a[n][k] if k == "classes" else [a[n][k]]) != \
                    sorted(map(tuple, b[n].get(k, [])) if k == "funcs" else b[n].get(k, []) if k == "classes" else [b[n].get(k)]):
                diff[k] += 1
    return diff


def main():
    tree = sys.argv[2]
    i = sys.argv.index("--")
    targets, out = sys.argv[3:i], sys.argv[i + 1]
    extra = {k: v for k, v in os.environ.items() if k.startswith("COVMAP_")}
    res = {"tree": tree, "targets": targets}
    reps = int(os.environ.get("REPS", "1"))
    for name, plugin in (("plain", None), ("setprofile", "covplugin"), ("monitoring", "covplugin_mon")):
        ts = [run(tree, targets, plugin, os.path.join(S, f"ov_{name}.json"), extra) for _ in range(reps)]
        res[name + "_s"] = round(min(ts), 2)
        print(name, ts, flush=True)
    a, b = (json.load(open(os.path.join(S, f"ov_{n}.json"))) for n in ("setprofile", "monitoring"))
    res["tests"] = len(a) - 1
    res["map_diff"] = same(a, b)
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res), flush=True)


if __name__ == "__main__":
    main()
