"""Free check before paid agent runs: does Proviso narrow the tests on each task the way it should?

For every task, the task's real fix (source files only) is applied to the base tree used for the assets, with a
generated version module as `pip install -e .` would write one, and Proviso selects tests against the task's
dependency map and base snapshot. A selection of ~90% on most tasks means something still makes everything look
affected (the false alarm fixed in FORMAT 11), and the paid runs would test nothing.

Usage: python research/agent/preflight_selection.py EVAL_DIR      (exit status 1 if the median share is >= 0.85)"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
from dc_engine import impact as I  # noqa: E402
from dc_eval.tasks import load_tasks  # noqa: E402

LIMIT = float(os.environ.get("PROVISO_PREFLIGHT_MAX_MEDIAN", "0.85"))


def git(cwd, *a, check=True):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=check).stdout


def main():
    eval_dir = os.path.abspath(sys.argv[1])
    shares = []
    for t in load_tasks(eval_dir):
        tree = os.path.join(eval_dir, "cache", "build", t.id[:10])
        assets = os.path.join(eval_dir, "impact", t.id)
        if not os.path.isdir(tree) or not os.path.isfile(os.path.join(assets, "covmap.json")):
            print(f"{t.id[:40]:40s} no assets; run build_assets.py first")
            continue
        git(tree, "checkout", "-q", "-f", t.commit)
        git(tree, "clean", "-q", "-fdx")
        os.makedirs(os.path.join(tree, ".dc-engine"), exist_ok=True)
        snap = os.path.join(assets, "importstate_base.json")
        if os.path.isfile(snap):
            subprocess.run(["cp", snap, os.path.join(tree, ".dc-engine", "importstate_base.json")], check=True)
        diff = git(tree, "diff", t.commit, t.fix_commit, "--", ".", ":(exclude)tests")
        subprocess.run(["git", "apply", "-"], cwd=tree, input=diff, text=True, check=True)
        pkg = sorted({p.split("/", 1)[0] for p in git(tree, "diff", "--name-only").split() if "/" in p})[:1]
        if pkg:
            with open(os.path.join(tree, pkg[0], "_version.py"), "w") as fh:
                fh.write('__version__ = version = "0.0.0.dev0"\n__version_tuple__ = version_tuple = (0, 0, 0)\n')
        cov = json.load(open(os.path.join(assets, "covmap.json")))
        try:
            sel, why = I.selection(tree, cov, sys.executable)
        finally:
            git(tree, "checkout", "-q", "-f", t.commit)
            git(tree, "clean", "-q", "-fdx", "-e", ".dc-engine")
        n = sum(1 for k in cov if not k.startswith("__"))
        share = 1.0 if sel is None else len(sel) / max(1, n)
        shares.append(share)
        noise = [k for k in why.get("import_state_changed", []) if k.endswith(":logger") or k.endswith(":_version")]
        print(f"{t.id[:40]:40s} selects {'all' if sel is None else len(sel):>5} of {n} ({share:.0%})"
              f"{'  reason: ' + why['reason'] if sel is None and why.get('reason') else ''}"
              f"{'  LOGGER/VERSION NOISE: ' + str(noise[:3]) if noise else ''}")
    if not shares:
        sys.exit("no task could be checked")
    med = statistics.median(shares)
    print(f"\nmedian share selected: {med:.0%} (limit {LIMIT:.0%})")
    if med >= LIMIT:
        sys.exit("Proviso selects nearly everything on most tasks; not starting paid runs.")


if __name__ == "__main__":
    main()
