"""Reproduce NameRTS's published RQ1 results through THIS study's NameRTS setup (research/v2/namerts_driver.py,
called exactly as the evaluation pipeline calls it). If our setup selects what NameRTS's own runs selected, the
NameRTS rows of our evaluation are trustworthy; if not, they are not.

For each of the first N target commit pairs of a project in NameRTS's dataset (dataset/commit_pairs_<p>.json):
  init on true_parent (fresh cache) -> check out current -> select (test files)
and compare with NameRTS's ground truth (ground truth/gt_<p>.json: tests_to_run) and with its published selection
(results/rq1/namerts/NameBDP_RTSTest_<code>.json), as in its paper: safe = every ground-truth test file selected.

Usage (inside WSL, in the repository, after run_all.sh's set-up):
  python research/v2/namerts_repro.py loguru 20
Results: research/v2/results/namerts_repro/<project>.jsonl and a printed summary. Resumable."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
proj, N = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 20
sys.argv = [sys.argv[0]]
sys.path.insert(0, HERE)
import pipeline as P  # noqa: E402

# project settings as in NameRTS's build_env.md; the same knobs our five repositories use
PROJECTS = {
    "loguru": dict(url="https://github.com/Delgan/loguru.git", code="LOG", gt="gt_loguru.json",
                   pairs="commit_pairs_loguru.json", pkg="loguru", targets=["tests"], test_dirs="tests",
                   pip=["freezegun", "exceptiongroup"]),
    "sympy": dict(url="https://github.com/sympy/sympy.git", code="SY", gt="gt_sympy.json",
                  pairs="commit_pairs_sympy.json", pkg="sympy", targets=["sympy"], test_dirs="sympy",
                  pip=["hypothesis", "mpmath"]),
}
C = PROJECTS[proj]
# NameRTS's own runs used 30-50 isolated workers; the worker count changes speed, not what is selected
os.environ.setdefault("NAMERTS_WORKERS", str(max(2, P.WORKERS)))
P.REPOS[f"nr-{proj}"] = dict(url=C["url"], commit="HEAD", pkg=C["pkg"], targets=C["targets"], mutate=None,
                             test_dirs=C["test_dirs"], pythonpath=[], pytest_args=[], before_test="",
                             nr_repo=proj, pip=[])
P.use(f"nr-{proj}")
NR = P.nr_env()["NAMERTS_HOME"]
OUT = os.path.join(HERE, "results", "namerts_repro")
os.makedirs(OUT, exist_ok=True)
out_path = os.path.join(OUT, f"{proj}.jsonl")


def git(tree, *a):
    return subprocess.run(["git", *a], cwd=tree, capture_output=True, text=True, check=True).stdout


def main():
    subprocess.run([P.PY, "-m", "pip", "install", "-q", *C["pip"]], check=False)
    repo = os.path.join(P.WORK, "repo")
    if not os.path.isdir(os.path.join(repo, ".git")):
        subprocess.run(["git", "clone", "-q", C["url"], repo], check=True)
    pairs = [p for p in json.load(open(os.path.join(NR, "dataset", C["pairs"]))) if p[3]][:N]
    gt = {(g["true_parent"], g["current"]): set(g["tests_to_run"])
          for g in json.load(open(os.path.join(NR, "ground truth", C["gt"])))}
    pub = {(r["true_parent"], r["current"]): set(r["tests_to_run"])
           for r in json.load(open(os.path.join(NR, "results", "rq1", "namerts", f"NameBDP_RTSTest_{C['code']}.json")))}
    done = {json.loads(l)["current"] for l in open(out_path)} if os.path.exists(out_path) else set()
    for direct_parent, true_parent, current, _ in pairs:
        if current in done:
            continue
        key = (true_parent, current)
        cache = os.path.join(P.WORK, "cache", true_parent[:12])
        row = {"current": current, "true_parent": true_parent}
        try:
            git(repo, "checkout", "-q", "-f", true_parent)
            git(repo, "clean", "-q", "-fdx")
            P.namerts("init", repo, cache)
            git(repo, "checkout", "-q", "-f", current)
            sel = set(P.namerts("select", repo, cache))
            truth, theirs = gt.get(key, set()), pub.get(key)
            row.update(selected=len(sel), truth=len(truth), safe=truth <= sel,
                       missed=sorted(truth - sel)[:20],
                       published_selected=None if theirs is None else len(theirs),
                       published_safe=None if theirs is None else truth <= theirs,
                       jaccard_vs_published=None if not theirs and not sel else
                       round(len(sel & (theirs or set())) / max(1, len(sel | (theirs or set()))), 3))
        except Exception as e:  # noqa: BLE001
            row["error"] = repr(e)[:400]
        with open(out_path, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        print(json.dumps({k: v for k, v in row.items() if k != "missed"}), flush=True)
    summary()


def summary():
    rows = [json.loads(l) for l in open(out_path)]
    ok = [r for r in rows if "error" not in r]
    print(f"\n== NameRTS reproduction on {proj}: {len(ok)} pairs scored, {len(rows) - len(ok)} errors")
    if not ok:
        return
    pub = [r for r in ok if r["published_safe"] is not None]
    print(f"safe rate, our setup:       {sum(r['safe'] for r in ok)}/{len(ok)}")
    print(f"safe rate, published runs:  {sum(r['published_safe'] for r in pub)}/{len(pub)}")
    js = [r["jaccard_vs_published"] for r in ok if r["jaccard_vs_published"] is not None]
    if js:
        print(f"overlap with published selection (Jaccard): mean {sum(js) / len(js):.2f}, "
              f"identical on {sum(1 for j in js if j == 1.0)}/{len(js)}")
    print("mean test files selected, ours vs published:",
          round(sum(r["selected"] for r in ok) / len(ok), 1), "vs",
          round(sum(r["published_selected"] or 0 for r in pub) / max(1, len(pub)), 1))


if __name__ == "__main__":
    main()
