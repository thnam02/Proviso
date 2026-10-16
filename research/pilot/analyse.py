"""Pilot analysis: does Proviso remove self-testing turns, and does cost fall with regressions at zero?

Usage: python research/pilot/analyse.py EVAL_DIR [EVAL_DIR ...] > research/pilot/pilot_results.json

Per run, from results.jsonl plus the agent's stream.jsonl:
  test_cmds       Bash calls that run tests (pytest / unittest)
  full_suite_cmds of those, calls that run the whole suite (no file, node id or -k filter)
  test_requests   model requests that issue at least one test command
  test_tokens     all-in tokens (input + cache read + cache write + output) of those requests
"""

from __future__ import annotations

import glob
import json
import os
import re
import shlex
import sys

TEST_RE = re.compile(r"\bpytest\b|\bunittest\b")
SUITE_DIRS = {"tests", "tests/", ".", "./tests", "./tests/"}


def _segments(cmd: str):
    for part in re.split(r"&&|\|\||;|\n|\|", cmd):
        part = part.strip()
        if TEST_RE.search(part):
            yield part


def is_full_suite(segment: str) -> bool:
    try:
        toks = shlex.split(segment)
    except ValueError:
        toks = segment.split()
    if "pytest" in " ".join(toks):
        idx = next(i for i, t in enumerate(toks) if "pytest" in t)
        rest = toks[idx + 1:]
    else:
        idx = next((i for i, t in enumerate(toks) if t == "unittest"), None)
        if idx is None:
            return False
        rest = toks[idx + 1:]
        if rest and rest[0] == "discover":
            return True
    targets, skip = [], False
    for i, t in enumerate(rest):
        if skip:
            skip = False
            continue
        if t in ("-k", "-m", "-p", "-c", "--ignore", "--deselect", "-n", "--tb", "-x", "--maxfail", "-o", "--junitxml"):
            if t in ("-k", "--deselect"):
                return False
            skip = t not in ("-x",)
            continue
        if t.startswith("-"):
            if t.startswith("-k") or t.startswith("--deselect"):
                return False
            continue
        if t.startswith(("2>", ">", "/dev/")) or t in ("2>&1",):
            continue
        targets.append(t)
    return all(t.rstrip("/") in {s.rstrip("/") for s in SUITE_DIRS} for t in targets)


def stream_stats(path: str) -> dict:
    usage, tools = {}, {}
    order = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
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
            usage[mid] = m.get("usage") or usage.get(mid) or {}
            for c in m.get("content") or []:
                if c.get("type") == "tool_use" and c.get("name") == "Bash":
                    tools.setdefault(mid, []).append((c.get("input") or {}).get("command", ""))
    def tok(u):
        return sum(int(u.get(k) or 0) for k in
                   ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    total = sum(tok(usage[m]) for m in order)
    test_cmds = full = test_req = test_tok = 0
    for mid in order:
        segs = [s for cmd in tools.get(mid, []) for s in _segments(cmd)]
        if not segs:
            continue
        test_req += 1
        test_tok += tok(usage[mid])
        test_cmds += len(segs)
        full += sum(is_full_suite(s) for s in segs)
    return {"requests_stream": len(order), "tokens_stream": total, "test_cmds": test_cmds,
            "full_suite_cmds": full, "test_requests": test_req, "test_tokens": test_tok,
            "test_token_share": round(test_tok / total, 3) if total else 0.0}


KEEP = ("task", "arm", "rep", "model", "status", "resolved", "hidden_score", "regressions", "cost_usd",
        "model_requests", "tokens", "wall_time_s", "diff_size", "timed_out", "proviso_blocks", "proviso_hard",
        "proviso_soft", "proviso_test_regressions", "proviso_verifies", "proviso_verify_ms",
        "proviso_context_chars", "proviso_captures", "hook_errors")


def main(dirs: list[str]) -> list[dict]:
    rows = []
    for d in dirs:
        latest = {}
        for line in open(os.path.join(d, "results.jsonl")):
            r = json.loads(line)
            latest[(r["task"], r["arm"], r["rep"])] = r
        for r in latest.values():
            row = {k: r.get(k) for k in KEEP}
            row["eval_dir"] = os.path.basename(d.rstrip("/"))
            s = glob.glob(os.path.join(r["run_dir"], "stream.jsonl"))
            if s:
                row.update(stream_stats(s[0]))
            rows.append(row)
    return sorted(rows, key=lambda x: (x["task"], x["rep"], x["arm"]))


if __name__ == "__main__":
    json.dump(main(sys.argv[1:]), sys.stdout, indent=1)
