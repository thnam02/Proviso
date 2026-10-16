"""Feasibility: how often do agent patches change behaviour that the reference fix leaves unchanged?

For every verified task (eval/tasks_v2, eval/tasks_complex) and every saved agent run of it (any arm, any model):
  base, fix   behaviour of the base and reference-fix commits on the task's probes (replay.py)
  patch       behaviour of the agent's final source tree (the run's repo copy)
  U           probes whose output the agent changed but the reference fix did not ("unintended change")
  M           probes the reference fix changed where the agent's output differs from the fix's ("intended change
              missed or done differently")
Output: research/ripple/feasibility.json (per run) and a printed summary.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import replay as R  # noqa: E402

SRC = "/home/claude/sources/sqlglot"
W = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad/ripple"
EVAL_DIRS = sorted(d for d in glob.glob("/home/claude/eval-*") if os.path.isfile(os.path.join(d, "results.jsonl")))


def tree(sha: str, dest: str) -> str:
    if not os.path.isdir(os.path.join(dest, "sqlglot")):
        os.makedirs(dest, exist_ok=True)
        p = subprocess.run(["git", "archive", sha], cwd=SRC, stdout=subprocess.PIPE, check=True)
        subprocess.run(["tar", "x", "-C", dest], input=p.stdout, check=True)
    return dest


def main():
    tasks = {}
    for f in glob.glob(os.path.join(ROOT, "eval", "tasks_v2", "*.json")) + glob.glob(os.path.join(ROOT, "eval", "tasks_complex", "*.json")):
        t = json.load(open(f))
        tasks[t["id"]] = t
    runs = []
    for d in EVAL_DIRS:
        latest = {}
        for line in open(os.path.join(d, "results.jsonl")):
            r = json.loads(line)
            latest[(r["task"], r["arm"], r["rep"])] = r
        for r in latest.values():
            repo = os.path.join(r.get("run_dir") or "", "repo")
            if r["task"] in tasks and os.path.isdir(os.path.join(repo, "sqlglot")):
                runs.append((os.path.basename(d), r, repo))
    print(len(tasks), "tasks,", len(runs), "agent runs", flush=True)
    per_task = {}
    for tid in sorted({r["task"] for _, r, _ in runs}):
        t = tasks[tid]
        td = os.path.join(W, "trees", tid[:10])
        base = tree(t["commit"], os.path.join(td, "base"))
        fix = tree(t["fix_commit"], os.path.join(td, "fix"))
        probes = R.probes(R.corpus(base), R.ripple(base))
        pp = os.path.join(td, "probes.json")
        json.dump(probes, open(pp, "w"))
        bo, fo = os.path.join(td, "base_out.json"), os.path.join(td, "fix_diff.json")
        if not os.path.isfile(bo):
            R.run(base, pp, bo)
        if not os.path.isfile(fo):
            R.run(fix, pp, fo, bo)
        per_task[tid] = (probes, json.load(open(bo)), json.load(open(fo)), pp, bo)
        print(tid[:10], len(probes), "probes; fix changes", len(per_task[tid][2]), flush=True)
    rows = []
    for i, (ed, r, repo) in enumerate(runs):
        probes, base_out, fix_diff, pp, bo = per_task[r["task"]]
        out = os.path.join(W, "patch", f"{ed}__{r['task'][:10]}__{r['arm']}__{r['rep']}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if not os.path.isfile(out):
            try:
                R.run(repo, pp, out, bo)
            except Exception as e:  # noqa: BLE001
                print("ERR", out, str(e)[-200:], flush=True)
                continue
        pd = json.load(open(out))
        U = [k for k in pd if k not in fix_diff]
        M = [k for k in fix_diff if pd.get(k, base_out.get(k)) != fix_diff[k]]
        def kind(k):
            b, a = base_out.get(k, ""), pd[k]
            if not b.startswith("EXC") and a.startswith("EXC"):
                return "now_raises"
            if b.startswith("EXC") and not a.startswith("EXC"):
                return "now_parses"
            return "output_changed"
        rows.append({
            "eval_dir": ed, "task": r["task"], "arm": r["arm"], "rep": r["rep"], "model": r.get("model"),
            "hidden_score": r.get("hidden_score"), "regressions": r.get("regressions"),
            "probes": len(probes), "fix_changed": len(fix_diff), "patch_changed": len(pd),
            "U": len(U), "U_ripple": sum(probes[int(k)][0] != probes[int(k)][1] for k in U),
            "U_now_raises": sum(kind(k) == "now_raises" for k in U),
            "U_now_parses": sum(kind(k) == "now_parses" for k in U),
            "U_dialects": sorted({probes[int(k)][1] for k in U}),
            "M": len(M), "U_examples": [[*probes[int(k)], base_out.get(k), pd[k]] for k in U[:5]],
        })
        if i % 25 == 0:
            print(i, "runs replayed", flush=True)
    json.dump(rows, open(os.path.join(HERE, "feasibility.json"), "w"), indent=1)
    n = len(rows)
    withU = [x for x in rows if x["U"] > 0]
    print(f"\n{n} agent patches; {len(withU)} ({100*len(withU)/n:.0f}%) change behaviour the reference fix does not")
    print(f"  with a new exception: {sum(x['U_now_raises']>0 for x in rows)}; in an inheriting dialect only: "
          f"{sum(x['U_ripple']>0 for x in rows)}; caught by existing tests: {sum((x['regressions'] or 0)>0 for x in rows)}")


if __name__ == "__main__":
    main()
