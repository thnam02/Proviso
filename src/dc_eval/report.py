"""Aggregate run metrics, paired table, bootstrap CI."""

from __future__ import annotations

import json
import os
import random
import statistics
from typing import Any, Iterable

from . import ALL_ARMS, BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED
from .catalog import catalog_report_lines, load_catalogs
from .stream import est_result_tokens, metrics_from_stream
from .tasks import load_tasks, select_task_ids

TOOL_SIZE_KEYS = (
    "tool_result_chars",
    "tool_result_tokens",
    "tool_result_chars_total",
    "tool_result_tokens_total",
    "dc_engine_result_chars",
    "dc_engine_results",
    "dc_engine_largest",
    "model_requests",
    "tokens_per_request",
)

MIN_N_NOTE = 5

PAIRED_METRICS = (
    ("resolved_rate", "resolved rate"),
    ("regressions", "regressions"),
    ("tokens", "tokens (in+out)"),
    ("model_requests", "requests"),
    ("tokens_per_request", "tokens/request"),
    ("cost_usd", "cost (USD)"),
    ("wall_time_s", "wall time (s)"),
    ("read_chars", "read chars"),
    ("read_calls", "read calls"),
    ("dc_engine_calls", "dc-engine calls"),
    ("contracts_created", "contracts created"),
    ("contract_retries", "contract retries"),
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


def _run_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("task") or ""), str(row.get("arm") or ""), str(row.get("rep") or ""))


def latest_non_error_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Last non-setup_error row per task/arm/rep; if none, the last row."""
    any_last: dict[tuple[str, str, str], dict[str, Any]] = {}
    ok_last: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for row in rows:
        k = _run_key(row)
        if k not in any_last:
            order.append(k)
        any_last[k] = row
        if row.get("status") != "setup_error":
            ok_last[k] = row
    return [ok_last.get(k, any_last[k]) for k in order]


def latest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    last: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for row in rows:
        k = _run_key(row)
        if k not in last:
            order.append(k)
        last[k] = row
    return [last[k] for k in order]


def _is_excluded(row: dict[str, Any]) -> bool:
    if row.get("limited"):
        return True
    if row.get("contaminated") or row.get("status") == "contaminated":
        return True
    if row.get("status") in ("grading_error", "setup_error", "agent_error"):
        return True
    return False


def _included(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if not _is_excluded(r)]


def _engine_fp(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("dc_engine_git_commit") or ""),
        str(row.get("dc_engine_git_dirty") or ""),
        str(row.get("dc_engine_path") or ""),
    )


def engine_commit_groups(
    rows: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Preserve first-seen commit order."""
    order: list[str] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        commit = str(row.get("dc_engine_git_commit") or "")
        if commit not in groups:
            order.append(commit)
            groups[commit] = []
        groups[commit].append(row)
    return [(c, groups[c]) for c in order]


def _short_hash(value: str, n: int = 12) -> str:
    if not value:
        return "(none)"
    return value if len(value) <= n else value[:n]


def _engine_section(
    rows: list[dict[str, Any]],
    compared: list[dict[str, Any]],
) -> list[str]:
    if not any(_engine_fp(r) != ("", "", "") for r in rows):
        return []
    lines = ["## dc-engine versions", ""]
    lines.append("Runs grouped by dc-engine commit:")
    lines.append("")
    lines.append("| commit | dirty | path | runs |")
    lines.append("|---|---|---|---:|")
    order: list[tuple[str, str, str]] = []
    counts: dict[tuple[str, str, str], int] = {}
    for row in rows:
        fp = _engine_fp(row)
        if fp not in counts:
            order.append(fp)
            counts[fp] = 0
        counts[fp] += 1
    for commit, dirty, path in order:
        lines.append(
            f"| {_short_hash(commit) if commit else '(unknown)'} | "
            f"{_short_hash(dirty)} | {path or '(unknown)'} | {counts[(commit, dirty, path)]} |"
        )
    lines.append("")
    fps = {_engine_fp(r) for r in compared} if compared else {_engine_fp(r) for r in rows}
    if len(fps) > 1:
        commits = sorted({fp[0] or "(unknown)" for fp in fps})
        lines.append(
            "**Warning:** this comparison mixes dc-engine versions "
            f"(commits: {', '.join(commits)}). "
            "Do not treat arm differences as an ablation of one engine."
        )
        lines.append("")
    return lines


def _present_arms(rows: Iterable[dict[str, Any]]) -> list[str]:
    seen = {str(r.get("arm") or "") for r in rows}
    seen.discard("")
    ordered = [a for a in ALL_ARMS if a in seen]
    extra = sorted(seen - set(ALL_ARMS))
    return ordered + extra


def _tokens_per_request(row: dict[str, Any]) -> float | None:
    tpr = row.get("tokens_per_request")
    if tpr is not None:
        try:
            return float(tpr)
        except (TypeError, ValueError):
            pass
    tok = _tokens(row)
    nreq = row.get("model_requests")
    if tok is None or not nreq:
        return None
    try:
        n = float(nreq)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return float(tok) / n


def _tokens(row: dict[str, Any]) -> float | None:
    dash = row.get("dashboard_total_tokens")
    if dash is not None:
        try:
            return float(dash)
        except (TypeError, ValueError):
            pass
    if row.get("usage_missing"):
        return None
    keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    if row.get("runner") == "cursor" or row.get("cache_write_tokens") is not None:
        if any(row.get(k) is None for k in keys):
            if row.get("tokens") is not None:
                return _f(row.get("tokens"))
            return None
        return sum(_f(row.get(k)) for k in keys)
    if row.get("input_tokens") is None and row.get("output_tokens") is None:
        return None
    return _f(row.get("input_tokens")) + _f(row.get("output_tokens"))


def _median_key(items: list[dict[str, Any]], key: str) -> float | None:
    xs = []
    for r in items:
        v = r.get(key)
        if v is None:
            continue
        try:
            xs.append(float(v))
        except (TypeError, ValueError):
            continue
    return _median(xs)


def per_task_arm_summary(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    grouped = _group(_included(rows))
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for key, items in grouped.items():
        resolved = [_f(r.get("resolved")) for r in items]
        tok = [t for t in (_tokens(r) for r in items) if t is not None]
        out[key] = {
            "n": len(items),
            "resolved_rate": (sum(resolved) / len(resolved)) if resolved else 0.0,
            "regressions": _median([_f(r.get("regressions")) for r in items]),
            "tokens": _median(tok),
            "cost_usd": _median_key(items, "cost_usd"),
            "wall_time_s": _median_key(items, "wall_time_s"),
            "read_chars": _median_key(items, "read_chars"),
            "turns": _median_key(items, "turns"),
            "input_tokens": _median_key(items, "input_tokens"),
            "output_tokens": _median_key(items, "output_tokens"),
            "cache_read_tokens": _median_key(items, "cache_read_tokens"),
            "cache_write_tokens": _median_key(items, "cache_write_tokens"),
            "model_requests": _median_key(items, "model_requests"),
            "tokens_per_request": _median([
                t for t in (_tokens_per_request(r) for r in items) if t is not None
            ]),
            "read_calls": _median_key(items, "read_calls"),
            "dc_engine_calls": _median_key(items, "dc_engine_calls"),
            "contracts_created": _median_key(items, "contracts_created"),
            "contract_retries": _median_key(items, "contract_retries"),
        }
    return out


def _arm_totals(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    items = [r for r in _included(rows) if r.get("arm") == arm]
    n = len(items)
    resolved = sum(1 for r in items if r.get("resolved"))
    cost_vals = [_f(r.get("cost_usd")) for r in items if r.get("cost_usd") is not None]
    tok = [t for t in (_tokens(r) for r in items) if t is not None]
    estimated = any(r.get("cost_estimated") for r in items)
    reqs = [
        _f(r.get("model_requests"))
        for r in items if r.get("model_requests") is not None
    ]
    tpr = [t for t in (_tokens_per_request(r) for r in items) if t is not None]
    return {
        "n_runs": n,
        "resolved": resolved,
        "resolved_rate": (resolved / n) if n else 0.0,
        "regressions_sum": sum(int(_f(r.get("regressions"))) for r in items),
        "cost_sum": sum(cost_vals) if cost_vals else 0.0,
        "cost_estimated": estimated,
        "tokens_sum": sum(tok) if tok else 0.0,
        "tokens_mean": (sum(tok) / len(tok)) if tok else 0.0,
        "wall_time_sum": sum(_f(r.get("wall_time_s")) for r in items),
        "read_chars_sum": sum(_f(r.get("read_chars")) for r in items),
        "requests_mean": (sum(reqs) / len(reqs)) if reqs else 0.0,
        "tokens_per_request_mean": (sum(tpr) / len(tpr)) if tpr else 0.0,
        "read_calls_sum": sum(_f(r.get("read_calls")) for r in items),
        "dc_engine_calls_sum": sum(_f(r.get("dc_engine_calls")) for r in items),
        "contracts_created_sum": sum(_f(r.get("contracts_created")) for r in items),
        "contract_retries_sum": sum(_f(r.get("contract_retries")) for r in items),
    }


def paired_diffs(
    summary: dict[tuple[str, str], dict[str, Any]],
    metric: str,
    tasks: Iterable[str],
    arm: str = "layer",
    baseline: str = "baseline",
) -> list[float]:
    diffs: list[float] = []
    for tid in tasks:
        base = summary.get((tid, baseline), {}).get(metric)
        other = summary.get((tid, arm), {}).get(metric)
        if base is None or other is None:
            continue
        diffs.append(float(other) - float(base))
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


def _share(part: float | None, total: float | None) -> str:
    if part is None or total is None or total <= 0:
        return "n/a"
    return f"{100.0 * part / total:.1f}%"


def attach_tool_sizes(eval_dir: str, rows: list[dict[str, Any]]) -> None:
    """Fill per-tool result sizes from saved streams (no agent rerun)."""
    from .cursor_stream import metrics_from_cursor_stream

    for row in rows:
        if row.get("tool_result_chars") and row.get("model_requests") is not None:
            continue
        slot = str(row.get("run_dir") or "")
        if not slot:
            slot = os.path.join(
                eval_dir, "runs",
                str(row.get("task") or ""),
                str(row.get("arm") or ""),
                str(row.get("rep") or ""),
            )
        path = os.path.join(slot, "stream.jsonl")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        if not text.strip():
            continue
        runner = str(row.get("runner") or "")
        if runner == "cursor" or '"tool_call"' in text[:4000]:
            m = metrics_from_cursor_stream(text)
        else:
            m = metrics_from_stream(text)
        for k in TOOL_SIZE_KEYS:
            if k in m:
                row[k] = m[k]


def _sum_tool_chars(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        blob = row.get("tool_result_chars") or {}
        if not isinstance(blob, dict):
            continue
        for name, n in blob.items():
            try:
                out[str(name)] = out.get(str(name), 0) + int(n)
            except (TypeError, ValueError):
                continue
    return out


def _layer_largest_dc(rows: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("arm") or "") in ("", "baseline"):
            continue
        for hit in row.get("dc_engine_results") or []:
            if not isinstance(hit, dict):
                continue
            chars = hit.get("chars")
            try:
                chars_i = int(chars)
            except (TypeError, ValueError):
                continue
            items.append({
                "tool": str(hit.get("tool") or ""),
                "chars": chars_i,
                "tokens": int(hit.get("tokens") or est_result_tokens(chars_i)),
                "task": row.get("task"),
                "rep": row.get("rep"),
            })
    items.sort(key=lambda r: (-r["chars"], r["tool"]))
    return items[:n]


def _tool_size_section(rows: list[dict[str, Any]]) -> list[str]:
    if not any((r.get("tool_result_chars") or r.get("dc_engine_results")) for r in rows):
        return []
    lines = [
        "## Tool result sizes",
        "",
        "Size of the result text returned to the agent for each completed tool call "
        "(chars, ~tokens = chars/4). MCP calls are grouped by dc-engine tool name. "
        "Totals are summed over the runs below (including contaminated).",
        "",
    ]
    for arm in _present_arms(rows) or ("baseline", "layer"):
        arm_rows = [r for r in rows if r.get("arm") == arm]
        by = _sum_tool_chars(arm_rows)
        total = sum(by.values())
        lines.append(f"### {arm}")
        lines.append("")
        lines.append(f"Total returned chars: **{total}** (~{est_result_tokens(total)} tokens).")
        lines.append("")
        if not by:
            lines.append("No completed tool results recorded.")
            lines.append("")
            continue
        lines.append("| tool | chars | ~tokens |")
        lines.append("|---|---:|---:|")
        for name, n in sorted(by.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| {name} | {n} | {est_result_tokens(n)} |")
        lines.append("")
    largest = _layer_largest_dc(rows, 5)
    lines.append("### Layer: largest dc-engine responses")
    lines.append("")
    if not largest:
        lines.append("No dc-engine tool results on the layer arm.")
        lines.append("")
        return lines
    lines.append("| tool | chars | ~tokens | task | rep |")
    lines.append("|---|---:|---:|---|---:|")
    for hit in largest:
        lines.append(
            f"| {hit['tool']} | {hit['chars']} | {hit['tokens']} | "
            f"{hit.get('task')} | {hit.get('rep')} |"
        )
    lines.append("")
    return lines


def _model_request_section(rows: list[dict[str, Any]]) -> list[str]:
    if not any(r.get("model_requests") is not None for r in rows):
        return []
    lines = [
        "## Model requests",
        "",
        "A request is a distinct `model_call_id` when the stream has one, "
        "otherwise an assistant event. tokens/request = run tokens / requests.",
        "",
        "| task | arm | rep | requests | tokens | tokens/request |",
        "|---|---|---:|---:|---:|---:|",
    ]
    present = _present_arms(rows) or ["baseline", "layer"]
    by_arm: dict[str, list[float]] = {a: [] for a in present}
    tpr_arm: dict[str, list[float]] = {a: [] for a in present}
    tok_arm: dict[str, list[float]] = {a: [] for a in present}
    for r in rows:
        nreq = r.get("model_requests")
        tok = _tokens(r)
        tpr = r.get("tokens_per_request")
        if tpr is None and tok is not None and nreq:
            try:
                tpr = float(tok) / float(nreq)
            except (TypeError, ValueError):
                tpr = None
        lines.append(
            f"| {r.get('task')} | {r.get('arm')} | {r.get('rep')} | "
            f"{_fmt(nreq)} | {_fmt(tok)} | {_fmt(tpr)} |"
        )
        arm = str(r.get("arm") or "")
        if nreq is not None and arm in by_arm:
            try:
                by_arm[arm].append(float(nreq))
            except (TypeError, ValueError):
                pass
        if tok is not None and arm in tok_arm:
            tok_arm[arm].append(float(tok))
        if tpr is not None and arm in tpr_arm:
            tpr_arm[arm].append(float(tpr))
    lines.append("")
    lines.append("| arm | mean requests | mean tokens | mean tokens/request |")
    lines.append("|---|---:|---:|---:|")
    for arm in present:
        def _m(xs: list[float]) -> float | None:
            return (sum(xs) / len(xs)) if xs else None
        lines.append(
            f"| {arm} | {_fmt(_m(by_arm[arm]))} | {_fmt(_m(tok_arm[arm]))} | "
            f"{_fmt(_m(tpr_arm[arm]))} |"
        )
    lines.append("")
    return lines


def render_report(
    rows: list[dict[str, Any]],
    catalogs: dict[str, dict[str, Any]] | None = None,
) -> str:
    lines: list[str] = ["# dc-eval report", ""]
    if not rows:
        lines.append("No results. Run `dc-eval run` first.")
        lines.append("")
        return "\n".join(lines)

    latest = latest_rows(rows)
    rows_for_metrics = latest_non_error_rows(rows)
    limited_n = sum(1 for r in rows_for_metrics if r.get("limited"))
    grade_err_rows = [r for r in latest if r.get("status") == "grading_error"]
    setup_err_rows = [r for r in latest if r.get("status") == "setup_error"]
    agent_err_rows = [r for r in latest if r.get("status") == "agent_error"]
    contaminated_rows = [
        r for r in rows_for_metrics
        if r.get("contaminated") or r.get("status") == "contaminated"
    ]
    rows_m = _included(rows_for_metrics)
    tasks = sorted({str(r.get("task") or "") for r in rows_m} or {str(r.get("task") or "") for r in rows})
    summary = per_task_arm_summary(rows_m)
    cursorish = any(r.get("runner") == "cursor" for r in rows)
    estimated = any(r.get("cost_estimated") for r in rows_m)
    arms = _present_arms(rows_m) or _present_arms(rows)

    lines.extend(_engine_section(latest, rows_m))
    lines.append("## Per-arm summary")
    lines.append("")
    lines.append(
        "| arm | runs | resolved | requests | tokens | tokens/request | "
        "time | read calls | dc-engine calls | contracts created | contract retries |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for arm in arms:
        t = _arm_totals(rows_m, arm)
        lines.append(
            f"| {arm} | {t['n_runs']} | {t['resolved']} | "
            f"{_fmt(t['requests_mean'])} | {int(t['tokens_sum'])} | "
            f"{_fmt(t['tokens_per_request_mean'])} | {t['wall_time_sum']:.1f} | "
            f"{_fmt(t['read_calls_sum'])} | {_fmt(t['dc_engine_calls_sum'])} | "
            f"{_fmt(t['contracts_created_sum'])} | {_fmt(t['contract_retries_sum'])} |"
        )
    lines.append("")
    if limited_n:
        lines.append(f"{limited_n} run(s) marked **limited** (plan/usage cap) were excluded from totals.")
        lines.append("")
    if setup_err_rows:
        lines.append("## Setup errors")
        lines.append("")
        lines.append(
            f"{len(setup_err_rows)} run(s) failed before the agent started "
            "and were excluded from totals."
        )
        lines.append("")
        lines.append("| task | arm | rep | error |")
        lines.append("|---|---|---:|---|")
        for r in setup_err_rows:
            err = str(r.get("setup_error") or "").replace("|", "\\|")
            if len(err) > 120:
                err = err[:119] + "…"
            lines.append(
                f"| {r.get('task')} | {r.get('arm')} | {r.get('rep')} | {err} |"
            )
        lines.append("")
    if agent_err_rows:
        lines.append("## Agent errors")
        lines.append("")
        lines.append(
            f"{len(agent_err_rows)} run(s) exited without a result event "
            "and were excluded from totals."
        )
        lines.append("")
        lines.append("| task | arm | rep | error |")
        lines.append("|---|---|---:|---|")
        for r in agent_err_rows:
            err = str(r.get("agent_error") or "").replace("|", "\\|")
            if len(err) > 120:
                err = err[:119] + "…"
            lines.append(
                f"| {r.get('task')} | {r.get('arm')} | {r.get('rep')} | {err} |"
            )
        lines.append("")
    if grade_err_rows:
        lines.append("## Grading errors")
        lines.append("")
        lines.append(
            f"{len(grade_err_rows)} run(s) failed to grade and were excluded from totals."
        )
        lines.append("")
        lines.append("| task | arm | rep | error |")
        lines.append("|---|---|---:|---|")
        for r in grade_err_rows:
            err = str(r.get("grading_error") or "").replace("|", "\\|")
            if len(err) > 120:
                err = err[:119] + "…"
            lines.append(
                f"| {r.get('task')} | {r.get('arm')} | {r.get('rep')} | {err} |"
            )
        lines.append("")
    if contaminated_rows:
        lines.append("## Contaminated runs")
        lines.append("")
        lines.append(
            f"{len(contaminated_rows)} run(s) searched the web or fetched URLs "
            "and were excluded from the main comparison."
        )
        lines.append("")
        lines.append("| task | arm | rep | searches | fetches | queries / URLs |")
        lines.append("|---|---|---:|---:|---:|---|")
        for r in contaminated_rows:
            bits = list(r.get("web_queries") or []) + list(r.get("web_urls") or [])
            shown = "; ".join(str(b) for b in bits[:4])
            if len(bits) > 4:
                shown += f" (+{len(bits) - 4})"
            shown = shown.replace("|", "\\|")
            if len(shown) > 80:
                shown = shown[:79] + "…"
            if not shown:
                shown = "—"
            lines.append(
                f"| {r.get('task')} | {r.get('arm')} | {r.get('rep')} | "
                f"{int(r.get('web_search_count') or 0)} | "
                f"{int(r.get('web_fetch_count') or 0)} | {shown} |"
            )
        lines.append("")
    lines.extend(_tool_size_section(latest_non_error_rows(rows)))
    lines.extend(_model_request_section(latest_non_error_rows(rows)))
    lines.extend(catalog_report_lines(catalogs or {}))
    lines.append(
        "Resolved rate is the fraction of runs where every hidden test passed. "
        "Other per-task numbers below are **medians over repetitions** "
        "(resolved rate per task is the mean of 0/1 over reps)."
    )
    if estimated:
        lines.append(
            "Cost is **estimated** from `eval/prices.json` (fill in real per-million-token "
            "prices). It is not a billed amount."
        )
    if cursorish:
        lines.append(
            "Token totals prefer dashboard `Total Tokens` when `dc-eval import-usage` has "
            "been run; otherwise they are input + cache write + cache read + output. "
            "Turn count is **n/a**: Cursor `--output-format stream-json` has no turn field."
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

    compare_arms = [a for a in arms if a != "baseline"]
    if "layer" not in compare_arms and "layer" in {str(r.get("arm") or "") for r in rows}:
        compare_arms.append("layer")
    for arm in compare_arms:
        lines.append(f"## Paired difference ({arm} − baseline) with 95% bootstrap CI")
        lines.append("")
        lines.append(
            f"Resamples: {BOOTSTRAP_RESAMPLES} with `random.choices`, seed {BOOTSTRAP_SEED}. "
            "Each observation is one task (median/rate over its reps). "
            f"Negative cost or tokens means the {arm} arm was cheaper/smaller."
        )
        lines.append("")
        n_pairs = 0
        for metric, _label in PAIRED_METRICS:
            diffs = paired_diffs(summary, metric, tasks, arm=arm)
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
            diffs = paired_diffs(summary, metric, tasks, arm=arm)
            ci = bootstrap_ci(diffs)
            if ci is None:
                lines.append(f"| {label} | 0 | — | — | — |")
                continue
            mean, lo, hi = ci
            lines.append(f"| {label} | {len(diffs)} | {mean:.4f} | {lo:.4f} | {hi:.4f} |")
        lines.append("")

    if cursorish:
        lines.append("## Token breakdown (median over reps)")
        lines.append("")
        lines.append(
            "Cache reads are the agent re-reading its own context and often dominate. "
            "Shares are of that arm's total (input + cache write + cache read + output)."
        )
        lines.append("")
        lines.append("| task | arm | input | cache write | cache read | output | total | in % | cw % | cr % | out % |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for tid in tasks:
            for arm in arms:
                s = summary.get((tid, arm), {})
                tot = s.get("tokens")
                inp, cw, cr, outp = (
                    s.get("input_tokens"), s.get("cache_write_tokens"),
                    s.get("cache_read_tokens"), s.get("output_tokens"),
                )
                lines.append(
                    f"| {tid} | {arm} | {_fmt(inp)} | {_fmt(cw)} | {_fmt(cr)} | {_fmt(outp)} | "
                    f"{_fmt(tot)} | {_share(inp, tot)} | {_share(cw, tot)} | {_share(cr, tot)} | "
                    f"{_share(outp, tot)} |"
                )
        lines.append("")
        lines.append("## Per-run hooks and CLI vs dashboard tokens")
        lines.append("")
        lines.append(
            "Cursor's docs do not confirm that project hooks run in the CLI, so every "
            "run records **hooks active: yes/no** from `.dc-engine/hooks.log` in the run "
            "copy (yes = at least one hook call without an error). Calls, denials, "
            "stop follow-ups, and errors are counted from those JSON lines."
        )
        lines.append("")
        lines.append(
            "| task | arm | rep | hooks active | calls | denials | stop follow-ups | "
            "errors | events | CLI tokens | dashboard tokens | >5% mismatch |"
        )
        lines.append("|---|---|---:|---|---:|---:|---:|---:|---|---:|---:|---|")
        for r in latest:
            ha = r.get("hooks_active")
            if ha is True:
                ha_s = "yes"
            elif ha is False:
                ha_s = "no"
            else:
                ha_s = "n/a"
            events = r.get("hook_calls_by_event") or {}
            if isinstance(events, dict) and events:
                ev_s = ", ".join(f"{k}:{v}" for k, v in sorted(events.items()))
            else:
                ev_s = "—"
            cli = r.get("cli_total_tokens")
            if cli is None:
                cli = _tokens(r) if r.get("dashboard_total_tokens") is None else (
                    _f(r.get("input_tokens")) + _f(r.get("output_tokens"))
                    + _f(r.get("cache_read_tokens")) + _f(r.get("cache_write_tokens"))
                    if not r.get("usage_missing") else None
                )
            dash = r.get("dashboard_total_tokens")
            flag = "yes" if r.get("token_mismatch_gt_5pct") else ("—" if dash is None else "no")
            lines.append(
                f"| {r.get('task')} | {r.get('arm')} | {r.get('rep')} | {ha_s} | "
                f"{_fmt(r.get('hook_calls'))} | {_fmt(r.get('hook_denials'))} | "
                f"{_fmt(r.get('hook_stop_followups'))} | {_fmt(r.get('hook_errors'))} | "
                f"{ev_s} | {_fmt(cli)} | {_fmt(dash)} | {flag} |"
            )
        lines.append("")
        na_bits = []
        if all(r.get("turns") is None for r in rows_m):
            na_bits.append(
                "**turns: n/a** — the Cursor stream-json schema has no `num_turns` field "
                "(see https://cursor.com/docs/cli/reference/output-format.md)."
            )
        if na_bits:
            lines.append("## Metrics this runner cannot provide")
            lines.append("")
            lines.extend(na_bits)
            lines.append("")
    return "\n".join(lines)


def write_report(
    eval_dir: str,
    rows: list[dict[str, Any]] | None = None,
    task_ids: list[str] | None = None,
    exclude_ids: list[str] | None = None,
) -> str:
    if rows is None:
        rows = load_results(eval_dir)
    if task_ids or exclude_ids:
        universe = [t.id for t in load_tasks(eval_dir)]
        if not universe:
            universe = sorted({
                str(r.get("task") or "") for r in rows if r.get("task")
            })
        selected = set(select_task_ids(universe, include=task_ids, exclude=exclude_ids))
        rows = [r for r in rows if str(r.get("task") or "") in selected]
    attach_tool_sizes(eval_dir, rows)
    catalogs = load_catalogs()
    if catalogs:
        path_json = os.path.join(eval_dir, "tool_catalog.json")
        with open(path_json, "w", encoding="utf-8") as fh:
            json.dump(
                {m: {k: c.get(k) for k in (
                    "mode", "chars", "tokens", "tool_count",
                    "instructions", "instructions_chars",
                    "instructions_tokens", "instructions_words",
                    "tools", "text",
                )} for m, c in catalogs.items()},
                fh, indent=2,
            )
            fh.write("\n")
    text = render_report(rows, catalogs=catalogs)
    path = os.path.join(eval_dir, "report.md")
    os.makedirs(eval_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")
    return path
