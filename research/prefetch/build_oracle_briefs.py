"""Oracle briefs: what baseline agents read and ran before their first edit, per task.

For each task, every baseline run's main-agent tool calls up to (not including) the first request that
edits a file are collected with their results. Results were produced at the base commit (no edits had
happened yet). Run-specific paths are made repository-relative, identical calls are kept once, and the
brief is capped at BRIEF_CAP characters, taking runs in order.

Also appended: the tests that already fail at the base commit (agents otherwise spend requests confirming
this with git stash at the end).

Usage: python research/prefetch/build_oracle_briefs.py OUT_DIR TASK_PREFIX... -- EVAL_DIR...
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pilot"))
from breakdown import classify  # noqa: E402

BRIEF_CAP = 36000
RESULT_CAP = 6000  # per call
REPO_RE = re.compile(r"/home/claude/[^\s'\"]*?/runs/[^/\s]+/[^/\s]+/\d+/repo/?")
CD_RE = re.compile(r"^\s*cd\s+\S+\s*(&&|;|\n)\s*")


def rel(text: str) -> str:
    return REPO_RE.sub("", text)


def describe(name: str, inp: dict) -> str:
    if name == "Bash":
        cmd = CD_RE.sub("", rel(inp.get("command", "")))
        return "$ " + cmd.strip()
    if name == "Read":
        p = rel(inp.get("file_path", ""))
        rng = ""
        if inp.get("offset") or inp.get("limit"):
            start = int(inp.get("offset") or 1)
            rng = f" lines {start}-{start + int(inp.get('limit') or 2000) - 1}"
        return f"[read {p}{rng}]"
    if name == "Grep":
        return (f"[grep {inp.get('pattern')!r} in {rel(inp.get('path', '.')) or '.'}"
                f"{' (' + inp['glob'] + ')' if inp.get('glob') else ''}]")
    if name == "Glob":
        return f"[glob {inp.get('pattern')}]"
    return f"[{name} {json.dumps(inp)[:200]}]"


def pre_edit_calls(stream: str) -> list[tuple[str, str]]:
    order, calls, results, tu2mid = [], {}, {}, {}
    for line in open(stream, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("parent_tool_use_id"):
            continue
        if e.get("type") == "assistant":
            m = e["message"]
            if m["id"] not in calls:
                order.append(m["id"])
                calls[m["id"]] = []
            for c in m.get("content") or []:
                if c.get("type") == "tool_use":
                    calls[m["id"]].append((c["id"], c["name"], c.get("input") or {}))
                    tu2mid[c["id"]] = m["id"]
        elif e.get("type") == "user":
            for c in (e.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    body = c.get("content")
                    if isinstance(body, list):
                        body = "\n".join(x.get("text", "") for x in body if isinstance(x, dict))
                    results[c["tool_use_id"]] = str(body or "")
    out = []
    for mid in order:
        cs = calls[mid]
        if classify([(n, json.dumps(i)) for _, n, i in cs]) == "edit(+run)":
            break
        for tid, name, inp in cs:
            res = rel(results.get(tid, ""))
            if "<tool_use_error>" in res:
                continue  # a failed tool call carries nothing an agent needs
            if len(res) > RESULT_CAP:
                res = res[:RESULT_CAP] + f"\n… ({len(res) - RESULT_CAP} more characters)"
            out.append((describe(name, inp), res.rstrip()))
    return out


def build(task: str, eval_dirs: list[str], failing: list[str]) -> str:
    runs = []
    for d in eval_dirs:
        latest = {}
        for line in open(os.path.join(d, "results.jsonl")):
            r = json.loads(line)
            latest[(r["task"], r["arm"], r["rep"])] = r
        for (t, arm, rep), r in sorted(latest.items()):
            if t == task and arm == "baseline":
                s = os.path.join(r["run_dir"], "stream.jsonl")
                if os.path.isfile(s):
                    runs.append(s)
    seen, parts, size = set(), [], 0
    for s in runs:
        for head, res in pre_edit_calls(s):
            key = (head, res)
            if key in seen or res in {r for _, r in seen if len(r) > 200}:
                continue
            block = f"{head}\n{res}\n"
            if size + len(block) > BRIEF_CAP:
                continue
            seen.add(key)
            parts.append(block)
            size += len(block)
    if failing:
        parts.append("Tests that already fail at this commit, before any change (not caused by you):\n"
                     + "\n".join(f"- {f}" for f in failing) + "\n")
    return "\n".join(parts), len(runs)


if __name__ == "__main__":
    args = sys.argv[1:]
    sep = args.index("--")
    out_dir, prefixes, dirs = args[0], args[1:sep], args[sep + 1:]
    failing_map = {}
    fpath = os.path.join(out_dir, "base_failures.json")
    if os.path.isfile(fpath):
        failing_map = json.load(open(fpath))
    tasks = set()
    for d in dirs:
        for line in open(os.path.join(d, "results.jsonl")):
            t = json.loads(line)["task"]
            if any(t.startswith(p) for p in prefixes):
                tasks.add(t)
    os.makedirs(out_dir, exist_ok=True)
    for t in sorted(tasks):
        text, n = build(t, dirs, failing_map.get(t, []))
        with open(os.path.join(out_dir, t + ".md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"{t}: {n} baseline runs, {len(text)} chars")
