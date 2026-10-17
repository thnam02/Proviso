"""Baseline vs impact on the sympy tasks: correctness, cost, wall time, and time spent inside test commands.

Test time per run = sum of the durations (tool_use -> tool_result timestamps in stream.jsonl) of Bash calls that run
tests (pytest, bin/test, unittest). Usage: python analyse.py BASE_EVAL_DIR IMPACT_EVAL_DIR [OUT.json]
"""
import json, os, re, statistics as st, sys
from datetime import datetime

TEST_RE = re.compile(r"\bpytest\b|bin/test\b|\bunittest\b")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def test_time(stream):
    started, total, n = {}, 0.0, 0
    for line in open(stream):
        e = json.loads(line)
        if e.get("type") == "assistant" and e.get("timestamp"):
            for c in e["message"]["content"]:
                if c.get("type") == "tool_use" and c.get("name") == "Bash" and TEST_RE.search(c["input"].get("command", "")):
                    started[c["id"]] = ts(e["timestamp"])
        if e.get("type") == "user" and e.get("timestamp"):
            for c in e["message"].get("content", []) if isinstance(e["message"].get("content"), list) else []:
                if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id") in started:
                    total += ts(e["timestamp"]) - started.pop(c["tool_use_id"])
                    n += 1
    return total, n


def load(eval_dir):
    rows = {}
    for line in open(os.path.join(eval_dir, "results.jsonl")):
        r = json.loads(line)
        rows[(r["task"], r["rep"])] = r
    out = []
    for (task, rep), r in sorted(rows.items()):
        if r.get("status") != "ok":
            continue
        run = r.get("run_dir") or ""
        stream = os.path.join(run, "stream.jsonl")
        tt, nt = test_time(stream) if os.path.exists(stream) else (None, None)
        out.append({"task": task, "rep": rep, "arm": r["arm"], "resolved": r.get("resolved"),
                    "hidden_score": r.get("hidden_score"), "regressions": r.get("regressions"),
                    "cost": r.get("cost_usd"), "wall": r.get("wall_time_s"), "test_time": tt, "test_cmds": nt,
                    "requests": r.get("model_requests"), "intercepts": r.get("proviso_intercepts"),
                    "impact_ran": r.get("proviso_impact_tests_run"), "impact_scope": r.get("proviso_impact_suite"),
                    "impact_secs": r.get("proviso_impact_secs")})
    return out


def summary(rows, label):
    def m(k):
        v = [r[k] for r in rows if r[k] is not None]
        return (st.mean(v), st.median(v)) if v else (None, None)
    res = sum(bool(r["resolved"]) for r in rows)
    return {"arm": label, "runs": len(rows), "resolved": res, "regressions": sum(r["regressions"] or 0 for r in rows),
            **{f"{k}_mean": round(m(k)[0], 3) if m(k)[0] is not None else None for k in ("cost", "wall", "test_time", "requests")},
            **{f"{k}_median": round(m(k)[1], 3) if m(k)[1] is not None else None for k in ("cost", "wall", "test_time")}}


if __name__ == "__main__":
    base, imp = load(sys.argv[1]), load(sys.argv[2])
    common = {(r["task"], r["rep"]) for r in base} & {(r["task"], r["rep"]) for r in imp}
    base = [r for r in base if (r["task"], r["rep"]) in common]
    imp = [r for r in imp if (r["task"], r["rep"]) in common]
    for s in (summary(base, "baseline"), summary(imp, "impact")):
        print(json.dumps(s))
    sel = [r for r in imp if r["impact_scope"]]
    if sel:
        ran, scope = sum(r["impact_ran"] for r in sel), sum(r["impact_scope"] for r in sel)
        print(f"intercepted runs: {len(sel)}/{len(imp)}; tests run {ran} of {scope} in scope ({ran / scope:.0%})")
    # per task: mean test time, both arms
    tasks = sorted({r["task"] for r in base})
    for t in tasks:
        b = [r["test_time"] or 0 for r in base if r["task"] == t]
        i = [r["test_time"] or 0 for r in imp if r["task"] == t]
        print(f"{t[:40]:40s} test time base {st.mean(b):6.0f}s  impact {st.mean(i):6.0f}s")
    if len(sys.argv) > 3:
        json.dump({"baseline": base, "impact": imp}, open(sys.argv[3], "w"), indent=1)
