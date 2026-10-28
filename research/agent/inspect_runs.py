"""Did Proviso actually act during the agent study? Per run: the agent's test commands (from the Claude Code stream),
how many were broad (the ones Proviso rewrites) or narrow (left alone), how many Proviso intercepted, how many
selected runs it completed, and whether the blast-radius report reached the agent.

Usage (WSL, as the user that ran the study):  python research/agent/inspect_runs.py ~/proviso-work/agent
Writes research/agent/results/interception.json and prints a per-arm summary."""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
from dc_engine.impact import _SEG_SPLIT, _broad_targets  # noqa: E402

TEST_CMD = re.compile(r"\b(pytest|py\.test|unittest)\b")


def stream_events(path):
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            try:
                yield json.loads(line)
            except ValueError:
                continue
    except OSError:
        return


def commands_and_results(stream):
    """Bash commands the agent issued, and the text of every tool result it received."""
    cmds, results = [], []
    for ev in stream_events(stream):
        msg = ev.get("message") or {}
        for c in msg.get("content") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use" and c.get("name") in ("Bash", "bash"):
                cmds.append((c.get("input") or {}).get("command", ""))
            if c.get("type") == "tool_result":
                body = c.get("content")
                if isinstance(body, list):
                    body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                results.append(str(body or ""))
    return cmds, results


def proviso_log(repo):
    ev = collections.Counter()
    path = os.path.join(repo, ".dc-engine", "proviso.log")
    for e in stream_events(path):
        ev[e.get("event", "?")] += 1
    return ev


def main():
    w = os.path.abspath(os.path.expanduser(sys.argv[1]))
    rows = []
    for slot in sorted(glob.glob(os.path.join(w, "runs", "*", "*", "*"))):
        task, arm, rep = slot.split(os.sep)[-3:]
        cmds, results = commands_and_results(os.path.join(slot, "stream.jsonl"))
        tests = [c for c in cmds if TEST_CMD.search(c)]
        broad = [c for c in tests if any(_broad_targets(s) is not None for s in _SEG_SPLIT.split(c))]
        log = proviso_log(os.path.join(slot, "repo"))
        rows.append({"task": task, "arm": arm, "rep": rep, "bash_cmds": len(cmds), "test_cmds": len(tests),
                     "broad_test_cmds": len(broad), "intercepts": log.get("intercept", 0),
                     "impact_runs": log.get("impact_run", 0),
                     "proviso_outputs_seen": sum("[Proviso]" in r for r in results),
                     "reports_seen": sum("Your change affects:" in r for r in results),
                     "test_cmd_examples": tests[:3]})
    out = os.path.join(HERE, "results", "interception.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(rows, open(out, "w"), indent=1)
    print(f"{len(rows)} runs -> {out}\n")
    print(f"{'arm':16s} {'runs':>4s} {'test cmds':>9s} {'broad':>6s} {'intercepted':>11s} {'Proviso runs':>12s} "
          f"{'runs w/ Proviso output':>22s} {'runs w/ report':>14s}")
    for arm in ("baseline", "impact-noreport", "impact"):
        a = [r for r in rows if r["arm"] == arm]
        if not a:
            continue
        s = lambda k: sum(r[k] for r in a)
        print(f"{arm:16s} {len(a):4d} {s('test_cmds'):9d} {s('broad_test_cmds'):6d} {s('intercepts'):11d} "
              f"{s('impact_runs'):12d} {sum(1 for r in a if r['proviso_outputs_seen']):22d} "
              f"{sum(1 for r in a if r['reports_seen']):14d}")
    print("\nexamples of the agents' test commands:")
    for r in rows[:6]:
        print(" ", r["arm"], r["test_cmd_examples"][:2])


if __name__ == "__main__":
    main()
