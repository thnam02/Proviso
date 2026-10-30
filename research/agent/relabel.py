"""Regrade stored agent-study results with the corrected task labels: an existing test that the task's hidden test
patch edits checks the new behaviour, so its failure is not counted as a regression (dc_eval.grade now does this when
grading; this applies it to results graded before the fix, without new agent runs).

Usage: python research/agent/relabel.py RESULTS.jsonl SOURCE_CLONE [TASKS_DIR]
Writes RESULTS_relabelled.jsonl next to the input and prints a per-arm summary."""
from __future__ import annotations

import collections
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
from dc_eval.grade import tests_changed_by_patch  # noqa: E402
from dc_eval.tasks import load_task  # noqa: E402


def main():
    results, src = sys.argv[1], sys.argv[2]
    tasks_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "eval", "tasks")
    edited = {}
    for f in glob.glob(os.path.join(tasks_dir, "*.json")):
        t = load_task(f)

        def base(path, c=t.commit):
            r = subprocess.run(["git", "-C", src, "show", f"{c}:{path}"], capture_output=True, text=True)
            return r.stdout if r.returncode == 0 else None
        edited[t.id] = tests_changed_by_patch(t.test_patch, base)
    rows = [json.loads(l) for l in open(results)]
    out = []
    for r in rows:
        ed = edited.get(r["task"], set())
        regr = {k: v for k, v in (r.get("regression") or {}).items() if k.split("[", 1)[0] not in ed}
        relabelled = sorted(k for k, v in (r.get("regression") or {}).items() if k.split("[", 1)[0] in ed and not v)
        out.append({**r, "regression": regr, "regressions": sum(1 for v in regr.values() if not v),
                    "regressions_before_relabel": r.get("regressions"), "relabelled_failures": relabelled})
    dest = results.replace(".jsonl", "_relabelled.jsonl")
    with open(dest, "w") as fh:
        for r in out:
            fh.write(json.dumps(r) + "\n")
    print(f"{len(out)} runs -> {dest}")
    for arm in sorted({r["arm"] for r in out}):
        a = [r for r in out if r["arm"] == arm]
        print(f"  {arm:16s} runs with a regression: before {sum(1 for r in a if r['regressions_before_relabel'])}, "
              f"after {sum(1 for r in a if r['regressions'])}; relabelled failures: "
              f"{collections.Counter(x for r in a for x in r['relabelled_failures']).most_common(3)}")


if __name__ == "__main__":
    main()
