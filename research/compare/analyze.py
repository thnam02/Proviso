"""Aggregate the comparison: per repository and dataset, for every selector,
  unsafe     changes (with at least one failing test) where some failing test was not selected
  missed     failing tests (or test modules) not selected, out of all failing ones
  tests %    mean share of the in-scope tests selected, over all changes
  time %     mean share of the in-scope test time selected, over all changes (median in brackets)
Usage: python analyze.py OUT_SUMMARY.json IN.json..."""
import json, statistics as st, sys

ORDER = ["retest_all", "name_match", "static_imports", "file_coverage", "file_coverage_cc", "testmon", "testmon_cc",
         "namerts", "func_only", "func_file", "proviso"]
LABEL = {"retest_all": "Retest all", "name_match": "Name-matched test files", "static_imports": "Static import graph",
         "file_coverage": "File-level coverage", "file_coverage_cc": "File-level coverage (cache cleared)",
         "testmon": "pytest-testmon", "testmon_cc": "pytest-testmon (cache cleared)", "namerts": "NameRTS",
         "func_only": "Proviso, functions only", "func_file": "Proviso, file fallback", "proviso": "Proviso"}


def summarize(rows):
    out = []
    groups = {}
    for r in rows:
        groups.setdefault((r["repo"], r["dataset"]), []).append(r)
    for (repo, ds), rs in sorted(groups.items()):
        for sel in ORDER:
            x = [r for r in rs if r["selector"] == sel]
            if not x:
                continue
            bad = [r for r in x if r["truth"]]
            out.append({
                "repo": repo, "dataset": ds, "selector": sel, "changes": len(x), "changes_failing": len(bad),
                "unsafe": sum(1 for r in bad if r["missed"]),
                "failing": sum(r["truth"] for r in bad), "missed": sum(len(r["missed"]) for r in bad),
                "tests_pct": round(100 * st.mean(r["selected"] / r["universe"] for r in x), 1),
                "time_pct": round(100 * st.mean(r["time_share"] for r in x), 1),
                "time_pct_median": round(100 * st.median(r["time_share"] for r in x), 1),
            })
    return out


def table(summary):
    lines = []
    for key in sorted({(s["repo"], s["dataset"]) for s in summary}):
        ss = [s for s in summary if (s["repo"], s["dataset"]) == key]
        lines.append(f"\n### {key[0]}, {key[1]} changes: {ss[0]['changes']} changes, {ss[0]['changes_failing']} "
                     f"break existing tests ({ss[0]['failing']} failing tests)\n")
        lines.append("| selector | changes with a missed failure | failing tests missed | tests selected | test time selected (median) |")
        lines.append("|---|---|---|---|---|")
        for s in ss:
            lines.append(f"| {LABEL[s['selector']]} | {s['unsafe']} of {s['changes_failing']} | {s['missed']} of "
                         f"{s['failing']} | {s['tests_pct']}% | {s['time_pct']}% ({s['time_pct_median']}%) |")
    return "\n".join(lines)


if __name__ == "__main__":
    rows = [r for p in sys.argv[2:] for r in json.load(open(p))]
    summary = summarize(rows)
    json.dump(summary, open(sys.argv[1], "w"), indent=1)
    print(table(summary))
