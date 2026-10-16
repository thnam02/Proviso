"""Where do baseline tokens go? Classifies every main-agent model request by the tool calls it issues.

Usage: python research/pilot/breakdown.py EVAL_DIR [EVAL_DIR ...]

Categories (first match wins):
  edit(+run)  writes a file (Edit/Write tool, or a Bash call that writes: open(..,'w'), sed -i, cat >, tee),
              including edit commands that also run tests or prints
  test-only   runs pytest/unittest without editing: the only requests Proviso could remove
  probe       runs a python snippet without editing or testing
  explore     reads, greps, lists
  final/text  no tool call (the answer)
"""

from __future__ import annotations

import collections
import glob
import json
import os
import re
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyse import TEST_RE  # noqa: E402

EDIT = re.compile(r"open\([^)]*['\"]w|\.write\(|write_text|sed -i|cat\s*>>?|tee ")
KINDS = ("explore", "probe", "edit(+run)", "test-only", "final/text")


def tok(u):
    return sum(int(u.get(k) or 0) for k in
               ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


def classify(calls):
    if not calls:
        return "final/text"
    text = " ".join(c[1] for c in calls)
    if {c[0] for c in calls} & {"Edit", "Write", "MultiEdit"} or EDIT.search(text):
        return "edit(+run)"
    if TEST_RE.search(text):
        return "test-only"
    if re.search(r"python3? (-c|-\s*<<|-I)", text):
        return "probe"
    return "explore"


def run_breakdown(stream):
    usage, calls, order = {}, {}, []
    for line in open(stream, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "assistant" or e.get("parent_tool_use_id"):
            continue
        m = e.get("message") or {}
        mid = m.get("id")
        if not mid:
            continue
        if mid not in usage:
            order.append(mid)
        usage[mid] = m.get("usage") or {}
        for c in m.get("content") or []:
            if c.get("type") == "tool_use":
                calls.setdefault(mid, []).append((c["name"], json.dumps(c.get("input"))))
    total = sum(tok(usage[m]) for m in order) or 1
    share, count = collections.Counter(), collections.Counter()
    for mid in order:
        k = classify(calls.get(mid, []))
        share[k] += tok(usage[mid]) / total
        count[k] += 1
    return share, count


def main(dirs, arm="baseline"):
    shares, counts = collections.defaultdict(list), collections.defaultdict(list)
    for d in dirs:
        latest = {}
        for line in open(os.path.join(d, "results.jsonl")):
            r = json.loads(line)
            latest[(r["task"], r["arm"], r["rep"])] = r
        for r in latest.values():
            if r["arm"] != arm:
                continue
            s = glob.glob(os.path.join(r["run_dir"], "stream.jsonl"))
            if not s:
                continue
            share, count = run_breakdown(s[0])
            for k in KINDS:
                shares[k].append(share[k])
                counts[k].append(count[k])
    n = len(shares["explore"])
    out = {"arm": arm, "runs": n,
           "kinds": {k: {"token_share": round(st.mean(shares[k]), 3),
                         "requests": round(st.mean(counts[k]), 2)} for k in KINDS}}
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    arm = "baseline"
    if args and args[0].startswith("--arm="):
        arm = args.pop(0).split("=", 1)[1]
    json.dump(main(args, arm), sys.stdout, indent=1)
    print()
