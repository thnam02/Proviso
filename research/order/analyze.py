"""Time to first failure (results/order.json): per dataset, the median and mean seconds until the agent sees its first
failing test, and as a share of the full suite's time; how often each order finds the failure in the first 10% of the
full suite's time. Usage: python analyze.py [results/order.json]"""
import json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "results", "order.json")))
ORD = ("full_default", "full_cheap", "sel_default", "sel_cheap", "sel_ranked")
NAMES = {"full_default": "Full suite, default order", "full_cheap": "Full suite, fastest first", "sel_default": "Proviso selection, default order",
         "sel_cheap": "Proviso selection, fastest first", "sel_ranked": "Proviso selection, ranked"}
groups = {}
for r in rows:
    groups.setdefault(f"{r['repo']} {r['dataset']}", []).append(r)
groups["all"] = rows
print("| changes | order | median TTFF (s) | mean TTFF (s) | median share of full suite | found within 10% of full time | full selection time share (median) |")
print("|---|---|---|---|---|---|---|")
for g, rs in groups.items():
    for o in ORD:
        v = [r[o] for r in rs if r[o] is not None]
        sh = [r[o] / r["full_time"] for r in rs if r[o] is not None]
        miss = sum(r[o] is None for r in rs)
        early = sum(1 for s in sh if s <= 0.10)
        print(f"| {g} ({len(rs)}) | {NAMES[o]} | {statistics.median(v):.2f} | {statistics.mean(v):.2f} | "
              f"{100 * statistics.median(sh):.1f}% | {early}/{len(rs)} | "
              f"{100 * statistics.median(r['sel_time'] / r['full_time'] for r in rs):.1f}%"
              + (f" (not found: {miss})" if miss else "") + " |")
# per change: speed-up of ranked over the default order of the selection, and over the full suite
sp = [r["sel_default"] / r["sel_ranked"] for r in rows if r["sel_ranked"]]
sf = [r["full_default"] / r["sel_ranked"] for r in rows if r["sel_ranked"]]
print(f"\nranked vs selection default order: median x{statistics.median(sp):.1f}; ranked faster on "
      f"{sum(s > 1 for s in sp)}, equal {sum(s == 1 for s in sp)}, slower {sum(s < 1 for s in sp)} of {len(sp)}")
sc = [r["full_cheap"] / r["sel_ranked"] for r in rows if r["sel_ranked"]]
print(f"ranked vs full suite fastest first: median x{statistics.median(sc):.1f}; ranked faster on {sum(s > 1 for s in sc)}, "
      f"equal {sum(s == 1 for s in sc)}, slower {sum(s < 1 for s in sc)}")
print(f"ranked vs full suite default order: median x{statistics.median(sf):.1f}, geometric mean "
      f"x{statistics.geometric_mean(sf):.1f}")
