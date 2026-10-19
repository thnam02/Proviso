"""Intent check results.
Dataset: fixes (intended) and planted bugs: observable (behaviour differs from the fix alone) or no effect; caught by
the fix's tests or silent.
Judge (per model and view): flags on planted bugs with an observable effect (recall; split silent / caught by tests)
and false alarms on the real fixes; reference: the existing tests (they flag a bug iff it is caught).
Usage: python analyze.py"""
import collections, glob, json, os

HERE = os.path.dirname(os.path.abspath(__file__))

cases = [c for p in sorted(glob.glob(os.path.join(HERE, "data", "*.json"))) for c in json.load(open(p))]
fixes = [c for c in cases if c["variant"] == "fix"]
bugs = [c for c in cases if c["variant"] == "bug"]
obs = [c for c in bugs if c["label"] == "unintended"]
print(f"tasks {len(fixes)}; planted bugs {len(bugs)}: observable {len(obs)}, no effect on outputs/import state "
      f"{len(bugs) - len(obs)}")
print(f"  observable & caught by tests {sum(c['caught_by_tests'] for c in obs)}, observable & silent "
      f"{sum(not c['caught_by_tests'] for c in obs)}; no effect but caught by tests "
      f"{sum(c['caught_by_tests'] for c in bugs if c['label'] == 'no_effect')}")
print(f"  fixes with an empty behavioural diff: {sum(1 for c in fixes if not c['import_changes'] and not c['output_changes'])}")

print("\n| judge | view | bugs flagged (observable) | silent bugs flagged | caught bugs flagged | fixes flagged (false alarm) | unparsed | cost |")
print("|---|---|---|---|---|---|---|---|")
print(f"| existing tests | - | {sum(c['caught_by_tests'] for c in obs)}/{len(obs)} | 0/{sum(not c['caught_by_tests'] for c in obs)} | "
      f"{sum(c['caught_by_tests'] for c in obs)}/{sum(c['caught_by_tests'] for c in obs)} | 0/{len(fixes)} | - | - |")
for p in sorted(glob.glob(os.path.join(HERE, "results", "judge_*.jsonl"))):
    rows = [json.loads(l) for l in open(p)]
    if not rows:
        continue
    m, v = rows[0]["model"], rows[0]["view"]
    flag = lambda r: r["verdict"] == "unintended"
    u = [r for r in rows if r["label"] == "unintended"]
    s = [r for r in u if not r["caught_by_tests"]]
    k = [r for r in u if r["caught_by_tests"]]
    f = [r for r in rows if r["label"] == "intended"]
    print(f"| {m} | {v} | {sum(map(flag, u))}/{len(u)} | {sum(map(flag, s))}/{len(s)} | {sum(map(flag, k))}/{len(k)} | "
          f"{sum(map(flag, f))}/{len(f)} | {sum(r['verdict'] not in ('clean', 'unintended') for r in rows)} | "
          f"${sum(r['cost'] or 0 for r in rows):.2f} |")
