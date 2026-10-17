"""The nine mined ripple commits and their child checks (from research/ripple_mining/labelled_ripples_*.json)."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
MINING = os.path.join(os.path.dirname(HERE), "ripple_mining")
COMMITS = ["ba0bff3d91", "efbc5e220c", "5d997d94d8", "7f1cf60c88", "9114355463", "862fd55467", "4ada15a429",
           "a313c8bee1", "d7fd83a7dc"]
# which children of each commit regressed (others in the mined list for that commit are benign)
CHILDREN = {"ba0bff3d91": {"trino", "dune"}, "efbc5e220c": {"redshift", "materialize", "risingwave"},
            "5d997d94d8": {"doris"}, "7f1cf60c88": {"doris"}, "9114355463": {"starrocks"},
            "862fd55467": {"athena", "dune"}, "4ada15a429": {"materialize"}, "a313c8bee1": {"materialize"},
            "d7fd83a7dc": {"redshift"}}


def ripples():
    rows = []
    for f in ("labelled_ripples_800.json", "labelled_ripples_1600.json"):
        rows += json.load(open(os.path.join(MINING, f)))
    out = {}
    for x in rows:
        c = x["commit"][:10]
        if c in CHILDREN and x["child"] in CHILDREN[c]:
            out.setdefault(c, []).append(x)
    return out
