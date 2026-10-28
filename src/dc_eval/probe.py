"""Cheap live probe of dc-engine's fixed per-session token overhead."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from . import ARMS, DEFAULT_BUDGET_USD
from .catalog import catalog_report_lines, load_catalogs
from .gitutil import git, is_git_repo
from .report import _fmt, _tokens
from .run import archive_run_dirs, execute_run, existing_run_slots, resolve_repo
from .tasks import Task, load_tasks

OVERHEAD_PROMPT = "Reply with the single word OK. Do not call any tools."
OVERHEAD_TASK_ID = "overhead-ok"
OVERHEAD_REPS = 2
DEFAULT_TIMEOUT_S = 180


def _shop_fixture_src() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    engine_root = os.path.dirname(os.path.dirname(here))
    return os.path.join(engine_root, "tests", "fixtures", "shop")


def ensure_git_shop(dest: str) -> str:
    if is_git_repo(dest):
        return git(["rev-parse", "HEAD"], dest).stdout.strip()
    src = _shop_fixture_src()
    parent = os.path.dirname(dest)
    os.makedirs(parent, exist_ok=True)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    git(["init"], dest)
    git(["config", "user.email", "eval@test.local"], dest)
    git(["config", "user.name", "Eval Test"], dest)
    git(["config", "commit.gpgsign", "false"], dest)
    git(["add", "."], dest)
    git(["commit", "-m", "shop fixture"], dest)
    return git(["rev-parse", "HEAD"], dest).stdout.strip()


def resolve_overhead_shop(eval_dir: str) -> tuple[str, str]:
    for task in load_tasks(eval_dir):
        if task.id != "shop-reject-zero":
            continue
        if not task.repo or not task.commit:
            continue
        src = resolve_repo(task, eval_dir)
        if os.path.isdir(src):
            return src, task.commit
    dest = os.path.expanduser("~/dc-eval-fixtures/overhead-shop")
    return dest, ensure_git_shop(dest)


def _mean(xs: list[float]) -> float | None:
    if not xs:
        return None
    return sum(xs) / len(xs)


def render_overhead_report(
    rows: list[dict[str, Any]],
    *,
    model: str,
    runner: str,
    shop: str,
    catalogs: dict[str, dict[str, Any]] | None = None,
) -> str:
    catalogs = catalogs or {}
    lines = [
        "# dc-eval overhead probe",
        "",
        f"prompt: `{OVERHEAD_PROMPT}`",
        f"shop: `{shop}`",
        f"runner: {runner}  model: {model}",
        "",
        "## Runs",
        "",
        "| arm | rep | tokens | requests | tokens/request | status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    by_arm: dict[str, list[float]] = {"baseline": [], "layer": []}
    req_arm: dict[str, list[float]] = {"baseline": [], "layer": []}
    tpr_arm: dict[str, list[float]] = {"baseline": [], "layer": []}
    for row in rows:
        arm = str(row.get("arm") or "")
        tok = _tokens(row)
        nreq = row.get("model_requests")
        tpr = row.get("tokens_per_request")
        if tpr is None and tok is not None and nreq:
            try:
                tpr = float(tok) / float(nreq)
            except (TypeError, ValueError):
                tpr = None
        lines.append(
            f"| {arm} | {row.get('rep')} | {_fmt(tok)} | {_fmt(nreq)} | "
            f"{_fmt(tpr)} | {row.get('status')} |"
        )
        if tok is not None and arm in by_arm:
            by_arm[arm].append(float(tok))
        if nreq is not None and arm in req_arm:
            try:
                req_arm[arm].append(float(nreq))
            except (TypeError, ValueError):
                pass
        if tpr is not None and arm in tpr_arm:
            tpr_arm[arm].append(float(tpr))
    lines.append("")
    mb = _mean(by_arm["baseline"])
    ml = _mean(by_arm["layer"])
    overhead = (ml - mb) if mb is not None and ml is not None else None
    lines.append("## Fixed overhead")
    lines.append("")
    lines.append(f"mean baseline tokens: {_fmt(mb)}")
    lines.append(f"mean layer tokens: {_fmt(ml)}")
    lines.append(
        f"fixed overhead (layer − baseline): **{_fmt(overhead)}** tokens/session"
    )
    lines.append("")
    lines.append("## Tokens per request")
    lines.append("")
    lines.append("| arm | mean requests | mean tokens/request |")
    lines.append("|---|---:|---:|")
    for arm in ARMS:
        lines.append(
            f"| {arm} | {_fmt(_mean(req_arm[arm]))} | {_fmt(_mean(tpr_arm[arm]))} |"
        )
    lines.append("")
    lines.extend(catalog_report_lines(catalogs))
    return "\n".join(lines)


def probe_overhead(
    eval_dir: str,
    *,
    model: str,
    runner: str = "cursor",
    reps: int = OVERHEAD_REPS,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    agent_bin: str = "agent",
    claude_bin: str = "claude",
    execute=execute_run,
) -> dict[str, Any]:
    eval_dir = os.path.abspath(eval_dir)
    shop, commit = resolve_overhead_shop(eval_dir)
    task = Task(
        id=OVERHEAD_TASK_ID,
        repo=shop,
        commit=commit,
        prompt=OVERHEAD_PROMPT,
    )
    plan = [(task, arm, rep) for rep in range(1, reps + 1) for arm in ARMS]
    slots = existing_run_slots(eval_dir, plan)
    if slots:
        archive_run_dirs(eval_dir, slots)
    rows: list[dict[str, Any]] = []
    for rep in range(1, reps + 1):
        for arm in ARMS:
            row = execute(
                task, arm, rep,
                eval_dir=eval_dir, model=model, budget_usd=DEFAULT_BUDGET_USD,
                timeout_s=timeout_s, claude_bin=claude_bin, src_repo=shop,
                runner=runner, agent_bin=agent_bin, do_grade=False,
            )
            rows.append(row)
    catalogs = load_catalogs()
    report = render_overhead_report(
        rows, model=model, runner=runner, shop=shop, catalogs=catalogs,
    )
    os.makedirs(eval_dir, exist_ok=True)
    path = os.path.join(eval_dir, "overhead.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report)
        if not report.endswith("\n"):
            fh.write("\n")
    payload = {
        "task": OVERHEAD_TASK_ID,
        "prompt": OVERHEAD_PROMPT,
        "shop": shop,
        "commit": commit,
        "model": model,
        "runner": runner,
        "reps": reps,
        "rows": rows,
        "mean_baseline_tokens": _mean(
            [t for t in (_tokens(r) for r in rows if r.get("arm") == "baseline") if t is not None]
        ),
        "mean_layer_tokens": _mean(
            [t for t in (_tokens(r) for r in rows if r.get("arm") == "layer") if t is not None]
        ),
        "catalogs": {
            mode: {k: cat.get(k) for k in (
                "mode", "chars", "tokens", "tool_count",
                "instructions_chars", "instructions_tokens", "instructions_words",
            )}
            for mode, cat in catalogs.items()
        },
    }
    b, l = payload["mean_baseline_tokens"], payload["mean_layer_tokens"]
    payload["fixed_overhead_tokens"] = (
        (l - b) if b is not None and l is not None else None
    )
    with open(os.path.join(eval_dir, "overhead.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    return payload
