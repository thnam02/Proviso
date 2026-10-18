"""Score every selector on one change. Returns one row per selector:
{selector, selected, universe, time_share, truth, missed}."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rts as SEL  # noqa: E402


def score_change(ch, universe, truth, cov, ctx, skip=()):
    """universe: test ids in scope (base failures removed); truth: failing test ids (or modules) of the change."""
    tsum = lambda ns: sum(cov.get(n, {}).get("time", 0) or 0 for n in ns)
    total_t = tsum(universe) or 1e-9
    rows = []
    for name, fn in SEL.SELECTORS.items():
        if name in skip or (name.endswith("_cc") and "testmon_db_cc" not in ctx):
            continue
        s = fn(ch, universe, cov=cov, **ctx)
        rows.append({"selector": name, "selected": len(s), "universe": len(universe),
                     "time_share": round(tsum(s) / total_t, 4), "truth": len(truth),
                     "missed": SEL.missed(truth, s)})
    return rows
