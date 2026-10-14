"""Run baseline vs layer arms in isolated copies of the task repo."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any

from . import (
    ARMS,
    DEFAULT_BUDGET_USD,
    DEFAULT_MODEL,
    DEFAULT_REPS,
    DEFAULT_TIMEOUT_S,
    SAFETY_WARNING,
)
from .arms import claude_argv, write_layer_files, write_layer_repo_config
from .gitutil import git, git_root, is_git_repo, is_git_url, realpath
from .grade import grade_repo
from .stream import metrics_from_stream
from .tasks import Task, load_tasks


class SafetyError(RuntimeError):
    pass


def print_safety_warning(file=None) -> None:
    print(SAFETY_WARNING, file=file or sys.stderr)


def repo_is_working_copy(repo: str, cwd: str | None = None) -> bool:
    """True when `repo` is (or contains) the current working directory."""
    if is_git_url(repo) or not os.path.isdir(repo):
        return False
    cwd_r = realpath(cwd or os.getcwd())
    repo_r = realpath(repo)
    try:
        if os.path.samefile(cwd_r, repo_r):
            return True
    except OSError:
        pass
    return cwd_r == repo_r or cwd_r.startswith(repo_r + os.sep)


def resolve_repo(task: Task, eval_dir: str) -> str:
    repo = (task.repo or ".").strip()
    if is_git_url(repo):
        return clone_url(repo, eval_dir)
    eval_abs = os.path.abspath(eval_dir)
    if repo in (".", ""):
        candidates = [
            os.getcwd(),
            eval_abs,
            os.path.dirname(eval_abs),
            os.path.dirname(os.path.dirname(eval_abs)),
        ]
    elif os.path.isabs(repo):
        candidates = [repo]
    else:
        candidates = [
            os.path.join(os.getcwd(), repo),
            os.path.join(eval_abs, repo),
            os.path.join(os.path.dirname(eval_abs), repo),
        ]
    seen: set[str] = set()
    for cand in candidates:
        cand = os.path.abspath(cand)
        if cand in seen or not os.path.isdir(cand):
            continue
        seen.add(cand)
        if is_git_repo(cand):
            return git_root(cand)
    for cand in candidates:
        cand = os.path.abspath(cand)
        if os.path.isdir(cand):
            return cand
    raise FileNotFoundError(f"task {task.id}: repo not found: {task.repo}")


def clone_url(url: str, eval_dir: str) -> str:
    cache = os.path.join(eval_dir, "cache")
    os.makedirs(cache, exist_ok=True)
    name = url.rstrip("/").rstrip(".git").replace("://", "_").replace("/", "_").replace(":", "_")
    dest = os.path.join(cache, name)
    if is_git_repo(dest):
        git(["fetch", "--all"], cwd=dest, check=False, timeout=300)
        return dest
    git(["clone", url, dest], cwd=cache, timeout=600)
    return dest


def _fresh_copy(src_repo: str, commit: str, dest: str) -> None:
    """Fresh checkout of `commit` at `dest`. Never the caller's working copy."""
    if os.path.exists(dest):
        if is_git_repo(dest):
            git(["worktree", "remove", "--force", dest], cwd=src_repo, check=False, timeout=60)
        shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if is_git_repo(src_repo):
        r = git(
            ["worktree", "add", "--detach", "--force", dest, commit],
            cwd=src_repo, check=False, timeout=120,
        )
        if r.returncode == 0:
            return
        r2 = git(
            ["clone", "--shared", "--no-checkout", src_repo, dest],
            cwd=os.path.dirname(dest), check=False, timeout=120,
        )
        if r2.returncode == 0:
            git(["checkout", "--force", commit], cwd=dest, timeout=60)
            return
        proc = subprocess.run(
            ["git", "archive", "--format=tar", commit],
            cwd=src_repo, stdout=subprocess.PIPE, check=True,
        )
        os.makedirs(dest, exist_ok=True)
        subprocess.run(["tar", "-x", "-C", dest], input=proc.stdout, check=True)
        return
    shutil.copytree(src_repo, dest, dirs_exist_ok=True)


def run_setup(repo: str, setup: str, timeout: int = 600) -> None:
    if not setup or not setup.strip():
        return
    r = subprocess.run(
        setup, cwd=repo, shell=True, capture_output=True, text=True, timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"setup command failed ({r.returncode}): {setup}\n{r.stderr or r.stdout}"
        )


def plan_runs(
    tasks: list[Task],
    arms: tuple[str, ...] = ARMS,
    reps: int = DEFAULT_REPS,
) -> list[tuple[Task, str, int]]:
    """Interleave arms: for each task, for each rep, both arms (not all baseline first)."""
    plan: list[tuple[Task, str, int]] = []
    for task in tasks:
        for rep in range(1, reps + 1):
            for arm in arms:
                plan.append((task, arm, rep))
    return plan


def estimate_cost(n_runs: int, budget_usd: float) -> tuple[float, float]:
    """(rough typical, hard cap). Typical is a guess — agent cost varies a lot."""
    typical = n_runs * min(0.40, budget_usd)
    cap = n_runs * budget_usd
    return typical, cap


def format_plan(
    plan: list[tuple[Task, str, int]],
    *,
    model: str,
    budget_usd: float,
    timeout_s: int,
    eval_dir: str,
) -> str:
    n = len(plan)
    typical, cap = estimate_cost(n, budget_usd)
    lines = [
        f"eval dir: {os.path.abspath(eval_dir)}",
        f"runs: {n}  (interleaved arms, {timeout_s}s wall-clock timeout each)",
        f"model: {model}",
        f"budget cap: ${budget_usd:.2f} / run  (hard cap ${cap:.2f} via --max-budget-usd)",
        f"rough cost estimate: ${typical:.2f}–${cap:.2f}  (highly variable; not a quote)",
        "",
        "order:",
    ]
    for i, (task, arm, rep) in enumerate(plan, 1):
        lines.append(f"  {i:3d}. {task.id}  {arm:8s}  rep {rep}  base={task.commit[:10]}")
    return "\n".join(lines)


def _run_dir(eval_dir: str, task_id: str, arm: str, rep: int) -> str:
    return os.path.join(eval_dir, "runs", task_id, arm, str(rep))


def _require_api_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SafetyError(
            "ANTHROPIC_API_KEY is not set. Bare mode (`claude --bare`) does not "
            "use a Claude.ai subscription; export ANTHROPIC_API_KEY first."
        )


def _require_claude(bin_name: str) -> str:
    path = shutil.which(bin_name)
    if not path:
        raise SafetyError(
            f"Claude Code CLI not found ({bin_name!r}). Install it and ensure "
            "it is on PATH. Tests never call the real CLI; this is only for live runs."
        )
    return path


def _append_jsonl(path: str, row: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def execute_run(
    task: Task,
    arm: str,
    rep: int,
    *,
    eval_dir: str,
    model: str,
    budget_usd: float,
    timeout_s: int,
    claude_bin: str,
    src_repo: str,
) -> dict[str, Any]:
    slot = _run_dir(eval_dir, task.id, arm, rep)
    repo_dir = os.path.join(slot, "repo")
    if repo_is_working_copy(repo_dir):
        raise SafetyError(f"refusing to run in the working copy: {repo_dir}")
    if realpath(repo_dir) == realpath(os.getcwd()):
        raise SafetyError("run directory resolved to the current working directory")
    _fresh_copy(src_repo, task.commit, repo_dir)
    if repo_is_working_copy(repo_dir) or realpath(repo_dir) == realpath(src_repo):
        shutil.rmtree(repo_dir, ignore_errors=True)
        raise SafetyError(
            "refusing to run in the working copy; the isolated checkout resolved "
            f"to {repo_dir}"
        )
    run_setup(repo_dir, task.setup)
    mcp_path = settings_path = None
    if arm == "layer":
        mcp_path, settings_path = write_layer_files(slot)
        write_layer_repo_config(repo_dir)
    argv = claude_argv(
        task.prompt, arm,
        model=model, budget_usd=budget_usd,
        mcp_config=mcp_path, settings=settings_path,
        claude_bin=claude_bin,
    )
    with open(os.path.join(slot, "command.json"), "w", encoding="utf-8") as fh:
        json.dump({"argv": argv, "cwd": repo_dir}, fh, indent=2)
        fh.write("\n")
    stream_path = os.path.join(slot, "stream.jsonl")
    stderr_path = os.path.join(slot, "stderr.txt")
    t0 = time.monotonic()
    timed_out = False
    returncode = -1
    try:
        with open(stream_path, "w", encoding="utf-8") as out, open(
            stderr_path, "w", encoding="utf-8"
        ) as err:
            proc = subprocess.run(
                argv, cwd=repo_dir, stdout=out, stderr=err,
                timeout=timeout_s, env=os.environ.copy(),
            )
            returncode = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        returncode = -9
    wall = time.monotonic() - t0
    stream_text = ""
    if os.path.isfile(stream_path):
        with open(stream_path, encoding="utf-8") as fh:
            stream_text = fh.read()
    metrics = metrics_from_stream(stream_text, wall_time_s=wall)
    grade = grade_repo(task, repo_dir)
    stop_blocks = max(
        int(metrics.get("stop_hook_blocks_stream") or 0),
        int(grade.get("stop_hook_blocks_disk") or 0),
    )
    row: dict[str, Any] = {
        "task": task.id,
        "arm": arm,
        "rep": rep,
        "commit": task.commit,
        "repo": src_repo,
        "run_dir": slot,
        "returncode": returncode,
        "timed_out": timed_out,
        **metrics,
        "resolved": grade.get("resolved"),
        "regressions": grade.get("regressions"),
        "hidden": grade.get("hidden"),
        "regression": grade.get("regression"),
        "modified_tests": grade.get("modified_tests"),
        "diff_size": grade.get("diff_size"),
        "contracts_created": grade.get("contracts_created") if arm == "layer" else 0,
        "final_contract_score": grade.get("final_contract_score") if arm == "layer" else None,
        "stop_hook_blocks": stop_blocks if arm == "layer" else 0,
        "checkpoints_restored": metrics.get("checkpoints_restored") if arm == "layer" else 0,
    }
    with open(os.path.join(slot, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(row, fh, indent=2)
        fh.write("\n")
    return row


def run_eval(
    eval_dir: str,
    *,
    task_ids: list[str] | None = None,
    arms: tuple[str, ...] = ARMS,
    reps: int = DEFAULT_REPS,
    dry_run: bool = False,
    model: str = DEFAULT_MODEL,
    budget_usd: float = DEFAULT_BUDGET_USD,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    claude_bin: str = "claude",
) -> int:
    print_safety_warning()
    eval_dir = os.path.abspath(eval_dir)
    tasks = load_tasks(eval_dir, task_ids)
    if not tasks:
        print(f"no tasks in {os.path.join(eval_dir, 'tasks')}", file=sys.stderr)
        return 1
    plan = plan_runs(tasks, arms=arms, reps=reps)
    print(format_plan(plan, model=model, budget_usd=budget_usd, timeout_s=timeout_s, eval_dir=eval_dir))
    if dry_run:
        return 0
    _require_api_key()
    claude_path = _require_claude(claude_bin)
    for task in tasks:
        src = resolve_repo(task, eval_dir)
        if repo_is_working_copy(src):
            raise SafetyError(
                f"refusing to run: task {task.id!r} repo is the current working copy "
                f"({src}). Run dc-eval from another directory, or point the task at a clone."
            )
    results_path = os.path.join(eval_dir, "results.jsonl")
    n_ok = 0
    for task, arm, rep in plan:
        src = resolve_repo(task, eval_dir)
        print(f"\n→ {task.id} {arm} rep {rep}", flush=True)
        row = execute_run(
            task, arm, rep,
            eval_dir=eval_dir, model=model, budget_usd=budget_usd,
            timeout_s=timeout_s, claude_bin=claude_path, src_repo=src,
        )
        _append_jsonl(results_path, row)
        n_ok += 1
        flag = "RESOLVED" if row.get("resolved") else "unresolved"
        cost = row.get("cost_usd")
        cost_s = f"${cost:.4f}" if isinstance(cost, (int, float)) else "n/a"
        print(f"  {flag}  cost={cost_s}  time={row.get('wall_time_s', 0):.0f}s")
    print(f"\nwrote {n_ok} rows to {results_path}")
    return 0
