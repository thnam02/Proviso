"""Match a Cursor dashboard usage CSV to eval runs.

Columns (dashboard export): Date, Cloud Agent ID, Automation ID, Kind, Model,
Max Mode, Input (w/ Cache Write), Input (w/o Cache Write), Cache Read,
Output Tokens, Total Tokens, Cost.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

SLACK = timedelta(minutes=2)
MISMATCH_FRAC = 0.05

COL_IN_WITH = "Input (w/ Cache Write)"
COL_IN_WITHOUT = "Input (w/o Cache Write)"
COL_CACHE = "Cache Read"
COL_OUT = "Output Tokens"
COL_TOTAL = "Total Tokens"


def parse_iso(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _num(raw: Any) -> int:
    if raw is None:
        return 0
    s = str(raw).strip().replace(",", "")
    if s == "" or s.lower() in ("n/a", "na", "-"):
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def parse_cost(raw: Any) -> Any:
    if raw is None:
        return ""
    s = str(raw).strip()
    if s.lower() in ("included", "free"):
        return s
    try:
        return float(s.replace("$", "").replace(",", ""))
    except ValueError:
        return s


def parse_csv_row(row: dict[str, str]) -> dict[str, Any]:
    in_w = _num(row.get(COL_IN_WITH))
    in_wo = _num(row.get(COL_IN_WITHOUT))
    cache = _num(row.get(COL_CACHE))
    out = _num(row.get(COL_OUT))
    summed = in_w + in_wo + cache + out
    reported = _num(row.get(COL_TOTAL))
    return {
        "date": row.get("Date") or "",
        "dt": parse_iso(row.get("Date") or ""),
        "cloud_agent_id": row.get("Cloud Agent ID") or "",
        "automation_id": row.get("Automation ID") or "",
        "kind": row.get("Kind") or "",
        "model": (row.get("Model") or "").strip(),
        "max_mode": row.get("Max Mode") or "",
        "input_with_cache_write": in_w,
        "input_without_cache_write": in_wo,
        "cache_read": cache,
        "output_tokens": out,
        "total_tokens_sum": summed,
        "total_tokens_reported": reported,
        "total_mismatch": reported != 0 and reported != summed,
        "cost": parse_cost(row.get("Cost")),
    }


def _model_match(run_model: str, row_model: str) -> bool:
    a = (run_model or "").strip().lower()
    b = (row_model or "").strip().lower()
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _run_window(run: dict[str, Any]) -> tuple[datetime, datetime] | None:
    start = parse_iso(str(run.get("started_at") or ""))
    end = parse_iso(str(run.get("ended_at") or ""))
    if start is None or end is None:
        return None
    if end < start:
        start, end = end, start
    return start - SLACK, end + SLACK


def load_runs(eval_dir: str) -> list[dict[str, Any]]:
    """Prefer results.jsonl; fall back to eval/runs/**/metrics.json."""
    path = os.path.join(eval_dir, "results.jsonl")
    rows: list[dict[str, Any]] = []
    if os.path.isfile(path):
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
    if rows:
        return rows
    runs_root = os.path.join(eval_dir, "runs")
    if not os.path.isdir(runs_root):
        return []
    for dirpath, _dirnames, filenames in os.walk(runs_root):
        if "metrics.json" not in filenames:
            continue
        try:
            with open(os.path.join(dirpath, "metrics.json"), encoding="utf-8") as fh:
                obj = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def match_rows(
    csv_rows: list[dict[str, Any]],
    runs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (assignments, ignored, ambiguous).

    assignments: csv row dicts with `run_index` set.
    A row matching two runs is ambiguous (not assigned).
    """
    assigned: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    windows = [_run_window(r) for r in runs]
    for crow in csv_rows:
        dt = crow.get("dt")
        if dt is None:
            ignored.append(crow)
            continue
        hits = []
        for i, run in enumerate(runs):
            win = windows[i]
            if win is None:
                continue
            if not (win[0] <= dt <= win[1]):
                continue
            if not _model_match(str(run.get("model") or ""), str(crow.get("model") or "")):
                continue
            hits.append(i)
        if len(hits) == 1:
            item = dict(crow)
            item["run_index"] = hits[0]
            assigned.append(item)
        elif len(hits) > 1:
            item = dict(crow)
            item["run_indexes"] = hits
            ambiguous.append(item)
        else:
            ignored.append(crow)
    return assigned, ignored, ambiguous


def _cli_tokens(run: dict[str, Any]) -> int | None:
    if run.get("tokens") is not None:
        try:
            return int(run["tokens"])
        except (TypeError, ValueError):
            pass
    parts = []
    for k in ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"):
        v = run.get(k)
        if v is None:
            return None
        try:
            parts.append(int(v))
        except (TypeError, ValueError):
            return None
    return sum(parts) if parts else None


def apply_dashboard_totals(
    runs: list[dict[str, Any]],
    assigned: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[int, list[dict[str, Any]]] = {}
    for row in assigned:
        buckets.setdefault(int(row["run_index"]), []).append(row)
    out = []
    for i, run in enumerate(runs):
        rec = dict(run)
        group = buckets.get(i) or []
        if not group:
            rec.setdefault("dashboard_total_tokens", None)
            rec.setdefault("token_mismatch_gt_5pct", False)
            out.append(rec)
            continue
        total = sum(int(r["total_tokens_sum"]) for r in group)
        rec["dashboard_total_tokens"] = total
        rec["dashboard_input_with_cache_write"] = sum(r["input_with_cache_write"] for r in group)
        rec["dashboard_input_without_cache_write"] = sum(r["input_without_cache_write"] for r in group)
        rec["dashboard_cache_read"] = sum(r["cache_read"] for r in group)
        rec["dashboard_output_tokens"] = sum(r["output_tokens"] for r in group)
        rec["dashboard_cost"] = [r["cost"] for r in group]
        rec["dashboard_rows"] = len(group)
        cli = _cli_tokens(rec)
        rec["cli_total_tokens"] = cli
        if cli is None or total <= 0:
            rec["token_mismatch_gt_5pct"] = bool(cli not in (None, 0) and total == 0)
        else:
            rec["token_mismatch_gt_5pct"] = abs(cli - total) / total > MISMATCH_FRAC
        out.append(rec)
    return out


def import_usage(csv_path: str, eval_dir: str) -> dict[str, Any]:
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        csv_rows = [parse_csv_row(r) for r in reader]
    runs = load_runs(eval_dir)
    assigned, ignored, ambiguous = match_rows(csv_rows, runs)
    updated = apply_dashboard_totals(runs, assigned)
    results_path = os.path.join(eval_dir, "results.jsonl")
    os.makedirs(eval_dir, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as fh:
        for row in updated:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    for row in updated:
        slot = row.get("run_dir")
        if not slot:
            continue
        mpath = os.path.join(slot, "metrics.json")
        if os.path.isfile(mpath):
            with open(mpath, "w", encoding="utf-8") as fh:
                json.dump(row, fh, indent=2, default=str)
                fh.write("\n")
    return {
        "csv_rows": len(csv_rows),
        "assigned": len(assigned),
        "ignored": len(ignored),
        "ambiguous": len(ambiguous),
        "runs": len(updated),
        "ambiguous_dates": [a.get("date") for a in ambiguous],
        "updated": updated,
    }
