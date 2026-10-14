"""Aggregate run metrics, paired table, bootstrap CI."""

from __future__ import annotations

import json
import os
import random
import statistics
from typing import Any, Iterable

from . import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED

MIN_N_NOTE = 5

PAIRED_METRICS = (
    ("resolved_rate", "resolved rate"),
    ("regressions", "regressions"),
    ("tokens", "tokens (in+out)"),
    ("cost_usd", "cost (USD)"),
    ("wall_time_s", "wall time (s)"),
    ("read_chars", "read chars"),
    ("turns", "turns"),
)


def bootstrap_ci(
    values: list[float],
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    alpha: float = 0.05,
) -> tuple[float, float, float] | None:
    """Mean and percentile 95% CI via `random.choices`. None if empty."""
    if not values:
        return None
    k = len(values)
    point = sum(values) / k
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_resamples):
        sample = rng.choices(values, k=k)
        means.append(sum(sample) / k)
    means.sort()
    lo_i = int((alpha / 2) * n_resamples)
    hi_i = int((1 - alpha / 2) * n_resamples) - 1
    lo_i = min(max(lo_i, 0), n_resamples - 1)
    hi_i = min(max(hi_i, 0), n_resamples - 1)
    return point, means[lo_i], means[hi_i]


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    return float(statistics.median(xs))


def _f(x: Any, default: float = 0.0) -> float:
    if x is None:
        return default
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def load_results(eval_dir: str) -> list[dict[str, Any]]:
    path = os.path.join(eval_dir, "results.jsonl")
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _group(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    g: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("task") or ""), str(row.get("arm") or ""))
        g.setdefault(key, []).append(row)
    return g


def _tokens(row: dict[str, Any]) -> float:
    return _f(row.get("input_tokens")) + _f(row.get("output_tokens"))


def per_task_arm_summary(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    grouped = _group(rows)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for key, items in grouped.items():
        resolved = [_f(r.get("resolved")) for r in items]
        out[key] = {
            "n": len(items),
            "resolved_rate": (sum(resolved) / len(resolved)) if resolved else 0.0,
            "regressions": _median([_f(r.get("regressions")) for r in items]),
            "tokens": _median([_tokens(r) for r in items]),
            "cost_usd": _median([_f(r.get("cost_usd")) for r in items if r.get("cost_usd") is not None]),
            "wall_time_s": _median([_f(r.get("wall_time_s")) for r in items]),
            "read_chars": _median([_f(r.get("read_chars")) for r in items]),
            "turns": _median([_f(r.get("turns")) for r in items]),
            "input_tokens": _median([_f(r.get("input_tokens")) for r in items]),
            "output_tokens": _median([_f(r.get("output_tokens")) for r in items]),
        }
    return out


def _arm_totals(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    items = [r for r in rows if r.get("arm") == arm]
    n = len(items)
    resolved = sum(1 for r in items if r.get("resolved"))
    cost_vals = [_f(r.get("cost_usd")) for r in items if r.get("cost_usd") is not None]
    return {
        "n_runs": n,
        "resolved": resolved,
        "resolved_rate": (resolved / n) if n else 0.0,
        "regressions_sum": sum(int(_f(r.get("regressions"))) for r in items),
        "cost_sum": sum(cost_vals) if cost_vals else 0.0,
        "tokens_sum": sum(_tokens(r) for r in items),
        "wall_time_sum": sum(_f(r.get("wall_time_s")) for r in items),
        "read_chars_sum": sum(_f(r.get("read_chars")) for r in items),
    }


def paired_diffs(
    summary: dict[tuple[str, str], dict[str, Any]],
    metric: str,
    tasks: Iterable[str],
) -> list[float]:
    diffs: list[float] = []
    for tid in tasks:
        base = summary.get((tid, "baseline"), {}).get(metric)
        layer = summary.get((tid, "layer"), {}).get(metric)
        if base is None or layer is None:
            continue
        diffs.append(float(layer) - float(base))
    return diffs


def _fmt(x: Any, money: bool = False) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if money:
        return f"${v:.4f}"
    if abs(v - round(v)) < 1e-9 and abs(v) < 1e6:
        return str(int(round(v)))
    return f"{v:.3f}"


def render_report(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = ["# dc-eval report", ""]
    if not rows:
        lines.append("No results. Run `dc-eval run` first.")
        lines.append("")
        return "\n".join(lines)

    tasks = sorted({str(r.get("task") or "") for r in rows})
    summary = per_task_arm_summary(rows)

    lines.append("## Per-arm totals")
    lines.append("")
    lines.append("| arm | runs | resolved | resolved rate | regressions | tokens | cost | wall time (s) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for arm in ("baseline", "layer"):
        t = _arm_totals(rows, arm)
        lines.append(
            f"| {arm} | {t['n_runs']} | {t['resolved']} | {t['resolved_rate']:.3f} | "
            f"{t['regressions_sum']} | {int(t['tokens_sum'])} | ${_f(t['cost_sum']):.4f} | "
            f"{t['wall_time_sum']:.1f} |"
        )
    lines.append("")
    lines.append(
        "Resolved rate is the fraction of runs where every hidden test passed. "
        "Other per-task numbers below are **medians over repetitions** "
        "(resolved rate per task is the mean of 0/1 over reps)."
    )
    lines.append("")

    lines.append("## Paired per-task (median over reps)")
    lines.append("")
    lines.append(
        "| task | resolved B | resolved L | regr B | regr L | tokens B | tokens L | "
        "cost B | cost L | time B | time L |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for tid in tasks:
        b = summary.get((tid, "baseline"), {})
        l = summary.get((tid, "layer"), {})
        lines.append(
            f"| {tid} | {_fmt(b.get('resolved_rate'))} | {_fmt(l.get('resolved_rate'))} | "
            f"{_fmt(b.get('regressions'))} | {_fmt(l.get('regressions'))} | "
            f"{_fmt(b.get('tokens'))} | {_fmt(l.get('tokens'))} | "
            f"{_fmt(b.get('cost_usd'), money=True)} | {_fmt(l.get('cost_usd'), money=True)} | "
            f"{_fmt(b.get('wall_time_s'))} | {_fmt(l.get('wall_time_s'))} |"
        )
    lines.append("")

    lines.append("## Paired difference (layer − baseline) with 95% bootstrap CI")
    lines.append("")
    lines.append(
        f"Resamples: {BOOTSTRAP_RESAMPLES} with `random.choices`, seed {BOOTSTRAP_SEED}. "
        "Each observation is one task (median/rate over its reps). "
        "Negative cost or tokens means the layer arm was cheaper/smaller."
    )
    lines.append("")
    n_pairs = 0
    for metric, _label in PAIRED_METRICS:
        diffs = paired_diffs(summary, metric, tasks)
        n_pairs = max(n_pairs, len(diffs))
    if n_pairs < MIN_N_NOTE:
        lines.append(
            f"**n = {n_pairs} paired task(s) — too small to conclude anything.** "
            "The interval below will be wide or degenerate; treat it as a smoke check, "
            f"not evidence. Aim for at least {MIN_N_NOTE} tasks."
        )
        lines.append("")
    lines.append("| metric | n | mean(L−B) | 95% CI low | 95% CI high |")
    lines.append("|---|---:|---:|---:|---:|")
    for metric, label in PAIRED_METRICS:
        diffs = paired_diffs(summary, metric, tasks)
        ci = bootstrap_ci(diffs)
        if ci is None:
            lines.append(f"| {label} | 0 | — | — | — |")
            continue
        mean, lo, hi = ci
        lines.append(f"| {label} | {len(diffs)} | {mean:.4f} | {lo:.4f} | {hi:.4f} |")
    lines.append("")
    return "\n".join(lines)


def write_report(eval_dir: str, rows: list[dict[str, Any]] | None = None) -> str:
    if rows is None:
        rows = load_results(eval_dir)
    text = render_report(rows)
    path = os.path.join(eval_dir, "report.md")
    os.makedirs(eval_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")
    return path
