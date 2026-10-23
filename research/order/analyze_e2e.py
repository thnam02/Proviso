"""End-to-end results (results/e2e.json), plain seconds, Proviso's warm selection time included.
Time to first failure (changes that break tests) and total time of a run (all changes, no stop at a failure).
Usage: python analyze_e2e.py"""
import json, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(HERE, "results", "e2e.json")))
groups = {}
for r in rows:
    groups.setdefault(f"{r['repo']} {r['dataset']}", []).append(r)
groups["all"] = rows
med = lambda xs: st.median(xs) if xs else float("nan")

print("Time to first failure, seconds (median / mean), changes that break tests")
print("| changes | full suite, pytest order | full suite, fastest first | Proviso (selection + ranked tests) | Proviso faster than full fastest-first |")
print("|---|---|---|---|---|")
for g, rs in groups.items():
    b = [r for r in rs if r["breaks"] and r["proviso_ranked"] is not None]
    if not b:
        continue
    f = lambda k: f"{med([r[k] for r in b]):.1f} / {st.mean([r[k] for r in b]):.1f}"
    win = sum(r["proviso_ranked"] < r["full_cheap"] for r in b)
    print(f"| {g} ({len(b)}) | {f('full_default')} | {f('full_cheap')} | {f('proviso_ranked')} | {win}/{len(b)} |")
print("\nProviso's selection time alone (median s):", {g: round(med([r["selection_s"] for r in rs]), 2) for g, rs in groups.items()})

print("\nTotal time of one run, seconds (median / mean), all changes")
print("| changes | full suite | Proviso (selection + selected tests) | Proviso faster on | median saving |")
print("|---|---|---|---|---|")
for g, rs in groups.items():
    f = lambda k: f"{med([r[k] for r in rs]):.1f} / {st.mean([r[k] for r in rs]):.1f}"
    win = sum(r["proviso_total"] < r["full_total"] for r in rs)
    sav = med([1 - r["proviso_total"] / r["full_total"] for r in rs])
    print(f"| {g} ({len(rs)}) | {f('full_total')} | {f('proviso_total')} | {win}/{len(rs)} | {100 * sav:.0f}% |")
