"""Variant briefs for checks B and C (see research/prefetch/README.md).

compact   Oracle brief cut to what agents used: reads of files that some baseline agent on the task went on to
          edit (source or test), plus snippets the agents ran (current behaviour), plus the pre-existing
          failures. Searches and listings are dropped. Capped at COMPACT_CAP characters (about 5k tokens).
failures  Only the pre-existing failures.

Usage: python research/prefetch/build_variant_briefs.py {compact|failures} OUT_DIR TASK_PREFIX... -- EVAL_DIR...
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_oracle_briefs import pre_edit_calls  # noqa: E402

COMPACT_CAP = 20000
FAILURES_HEAD = "Tests that already fail at this commit, before any change (not caused by you):\n"
READ_HEAD = re.compile(r"^\[read (\S+)|^\$ (?:sed -n|cat|head|tail|nl|awk)\b")
RANGE = re.compile(r"^\[read (\S+) lines (\d+)-(\d+)\]")
PROBE_HEAD = re.compile(r"^\$ .*\bpython3?\b.*(-c|<<)")


def edited_files(repo: str) -> set[str]:
    out = subprocess.run(["git", "-C", repo, "status", "--porcelain"], capture_output=True, text=True).stdout
    files = set()
    for line in out.splitlines():
        p = line[3:].strip().split(" -> ")[-1]
        if p and not p.startswith(".dc-engine"):
            files.add(p)
    return files


def baseline_runs(task: str, eval_dirs: list[str]) -> list[str]:
    runs = []
    for d in eval_dirs:
        latest = {}
        for line in open(os.path.join(d, "results.jsonl")):
            r = json.loads(line)
            latest[(r["task"], r["arm"], r["rep"])] = r
        for (t, arm, _), r in sorted(latest.items()):
            if t == task and arm == "baseline" and os.path.isfile(os.path.join(r["run_dir"], "stream.jsonl")):
                runs.append(r["run_dir"])
    return runs


def failures_block(failing: list[str]) -> str:
    return FAILURES_HEAD + "\n".join(f"- {f}" for f in failing) + "\n" if failing else ""


def compact(task: str, eval_dirs: list[str], failing: list[str]) -> str:
    runs = baseline_runs(task, eval_dirs)
    used = set()
    for r in runs:
        used |= edited_files(os.path.join(r, "repo"))
    cands, seen = [], set()
    for r in runs:
        for head, res in pre_edit_calls(os.path.join(r, "stream.jsonl")):
            first = head.splitlines()[0]
            is_read = bool(READ_HEAD.search(first)) and any(f in head for f in used)
            is_probe = bool(PROBE_HEAD.search(first)) and "open(" not in head
            if (is_read or is_probe) and res.strip() and res not in seen:
                seen.add(res)
                cands.append((head, res))
    # a read whose line range lies inside another read of the same file adds nothing
    spans = [(m.group(1), int(m.group(2)), int(m.group(3))) if (m := RANGE.match(h)) else None
             for h, _ in cands]
    keep = []
    for i, (h, res) in enumerate(cands):
        sp = spans[i]
        inside = sp and any(o and o != sp and o[0] == sp[0] and o[1] <= sp[1] and sp[2] <= o[2]
                            for o in spans)
        whole = sp and any(h2.startswith(f"[read {sp[0]}]") for h2, _ in cands)
        if not (inside or whole):
            keep.append((h, res))
    parts, size = [], 0
    for h, res in keep:
        block = f"{h}\n{res}\n"
        if size + len(block) > COMPACT_CAP:
            continue
        parts.append(block)
        size += len(block)
    tail = failures_block(failing)
    return "\n".join(parts + ([tail] if tail else []))


if __name__ == "__main__":
    args = sys.argv[1:]
    mode, out_dir = args[0], args[1]
    sep = args.index("--")
    prefixes, dirs = args[2:sep], args[sep + 1:]
    failing_map = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              "oracle_briefs", "base_failures.json")))
    os.makedirs(out_dir, exist_ok=True)
    for t in sorted(failing_map):
        if not any(t.startswith(p) for p in prefixes):
            continue
        text = compact(t, dirs, failing_map[t]) if mode == "compact" else failures_block(failing_map[t])
        with open(os.path.join(out_dir, t + ".md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"{mode} {t[:10]}: {len(text)} chars")
