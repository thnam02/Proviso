"""Does our NameRTS setup reproduce the paper's own selections? For the first N evaluated loguru commit pairs of the
replication package (dataset/commit_pairs_loguru.json), NameRTS is initialised at the pair's base ("true parent")
and run on the commit; the selected test files are compared with results/rq1/namerts/NameBDP_RTSTest_LOG.json.
(The paper's later pairs start from caches updated incrementally along the history, ours from a fresh init at the
base, so small differences are possible there; the first pair starts from a fresh init in both.)
Usage: python check_namerts_fidelity.py N OUT.json"""
import json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
NR = "/home/claude/tools/NameRTS"
W = "/home/claude/cmp/nrcheck"
n, out = int(sys.argv[1]), sys.argv[2]
pairs = [p for p in json.load(open(f"{NR}/dataset/commit_pairs_loguru.json")) if p[3]][:n]
paper = {r["current"]: sorted(r["tests_to_run"])
         for r in json.load(open(f"{NR}/results/rq1/namerts/NameBDP_RTSTest_LOG.json"))}
env = dict(os.environ, NAMERTS_EXTRA_PATH="/home/claude/tools/freezegun")
rows = []
for _, base, cur, _ in pairs:
    tree = os.path.join(W, "loguru")
    shutil.rmtree(tree, ignore_errors=True)
    shutil.copytree("/home/claude/tools/loguru", tree)
    g = lambda *a: subprocess.run(["git", *a], cwd=tree, capture_output=True)
    g("checkout", "-q", "-f", base)
    cache = os.path.join(W, f"cache-{base[:8]}")
    shutil.rmtree(cache, ignore_errors=True)
    r = subprocess.run(["python3", f"{HERE}/namerts_driver.py", "init", tree, cache, "loguru"], capture_output=True,
                       text=True, env=env)
    info = json.loads(r.stdout.strip().splitlines()[-1])
    g("checkout", "-q", cur)
    r = subprocess.run(["python3", f"{HERE}/namerts_driver.py", "select", tree, cache, "loguru"], capture_output=True,
                       text=True, env=env)
    ours = json.loads([l for l in r.stdout.splitlines() if l.startswith("NAMERTS_SELECTED ")][0][17:])
    theirs = paper.get(cur)
    rows.append({"base": base, "commit": cur, "init_test_time": info["test_time"], "ours": ours, "paper": theirs,
                 "same": ours == theirs})
    print(cur[:8], "init tests %.0fs" % info["test_time"], "ours", len(ours), "paper", len(theirs or []),
          "SAME" if ours == theirs else f"DIFF only-ours={sorted(set(ours) - set(theirs or []))} "
                                        f"only-paper={sorted(set(theirs or []) - set(ours))}", flush=True)
    json.dump(rows, open(out, "w"), indent=1)
