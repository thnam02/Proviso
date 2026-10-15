"""Run baseline vs layer arms in isolated copies of the task repo."""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from typing import Any, NamedTuple

from . import (
    ARMS,
    CONSECUTIVE_SETUP_STOP,
    DEFAULT_ARM_SEED,
    DEFAULT_BUDGET_USD,
    DEFAULT_MODEL,
    DEFAULT_REPS,
    DEFAULT_TIMEOUT_S,
    SAFETY_WARNING,
    SETUP_LOG,
)
from datetime import datetime, timezone

from .arms import (
    arm_config, arm_extras_note, claude_argv, cursor_argv,
    hook_command, server_mcp_args, write_layer_files, write_layer_repo_config,
)
from .cursor_stream import is_limit_error, metrics_from_cursor_stream, summarize_hooks_log
from .gitutil import (
    GitError,
    git,
    git_diff_hash,
    git_head,
    git_root,
    is_git_repo,
    is_git_url,
    realpath,
)
from .grade import grade_repo, install_test_env
from .prices import ensure_prices_file, estimate_cost_usd
from .stream import metrics_from_stream, stream_has_result
from .tasks import Task, load_tasks, select_tasks


class SafetyError(RuntimeError):
    pass


ENGINE_CHANGED = "dc-engine changed since batch start"


class EnginePin(NamedTuple):
    """dc-engine identity frozen at batch start."""

    git_commit: str | None
    git_dirty: str | None
    package_path: str
    version: str

    def as_metrics(self) -> dict[str, Any]:
        return {
            "dc_engine_version": self.version,
            "dc_engine_path": self.package_path,
            "dc_engine_git_commit": self.git_commit,
            "dc_engine_git_dirty": self.git_dirty,
        }

    def fingerprint(self) -> tuple[str | None, str | None, str]:
        return (self.git_commit, self.git_dirty, self.package_path)


def format_engine_pin(pin: EnginePin) -> str:
    commit = pin.git_commit or "unknown"
    dirty = pin.git_dirty or "unknown"
    if pin.git_dirty and len(pin.git_dirty) > 12:
        dirty = pin.git_dirty[:12]
    return f"dc-engine: commit={commit} dirty={dirty} path={pin.package_path}"


class SetupError(RuntimeError):
    """Failed before the agent started. Never report as unresolved."""


def _arm_tracks_contracts(arm: str) -> bool:
    return (arm or "").strip().lower() not in ("", "baseline")


def _apply_arm_meta(
    row: dict[str, Any],
    arm: str,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = arm_config(arm)
    row["dc_engine_tools"] = cfg.get("tools")
    row["hook_mode"] = cfg.get("hook_mode") or "off"
    m = metrics or {}
    row.setdefault("read_calls", int(m.get("read_calls") or 0))
    row.setdefault("dc_engine_calls", int(m.get("dc_engine_calls") or 0))
    dc_cc = int(m.get("dc_contract_calls") or row.get("dc_contract_calls") or 0)
    row["dc_contract_calls"] = dc_cc
    follow = int(m.get("hook_stop_followups") or row.get("hook_stop_followups") or 0)
    row["contract_retries"] = follow + max(0, dc_cc - 1)
    return row


WEBFETCH_DENY = "WebFetch(*)"
OFFLINE_RULE_REL = os.path.join(".cursor", "rules", "offline.mdc")
OFFLINE_RULE = """\
---
description: Work offline during eval runs
alwaysApply: true
---

# Offline eval

Work offline. Do not search the web or fetch URLs. Use only the repository and local tools.
"""


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
    repo = os.path.expanduser((task.repo or ".").strip())
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


def run_setup(
    repo: str,
    setup: str,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> None:
    if not setup or not setup.strip():
        return
    r = subprocess.run(
        setup, cwd=repo, shell=True, capture_output=True, text=True,
        timeout=timeout, env=env,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"setup command failed ({r.returncode}): {setup}\n{r.stderr or r.stdout}"
        )


def paths_overlap(a: str, b: str) -> bool:
    a, b = realpath(a), realpath(b)
    return a == b or a.startswith(b + os.sep) or b.startswith(a + os.sep)


def harness_src_dir() -> str:
    """Directory that contains the `dc_eval` and (in a source checkout) `dc_engine` packages."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dc_engine_source_root() -> str | None:
    """dc-engine checkout root (parent of `src/`) when running from a source tree."""
    src = harness_src_dir()
    engine_pkg = os.path.join(src, "dc_engine")
    eval_pkg = os.path.join(src, "dc_eval")
    if os.path.isfile(os.path.join(engine_pkg, "__init__.py")) and os.path.isdir(eval_pkg):
        return realpath(os.path.dirname(src))
    return None


def dc_engine_package_dir() -> str:
    """Filesystem path of the `dc_engine` package used by this interpreter."""
    sibling = os.path.join(harness_src_dir(), "dc_engine")
    init = os.path.join(sibling, "__init__.py")
    if os.path.isfile(init):
        return os.path.abspath(sibling)
    raise SafetyError(
        "dc-engine is not installed next to dc_eval in the harness interpreter "
        f"({sys.executable})"
    )


def dc_engine_meta() -> tuple[str, str]:
    """(version, package path) for run metadata. Does not import dc_engine."""
    pkg = dc_engine_package_dir()
    ver = "unknown"
    init = os.path.join(pkg, "__init__.py")
    try:
        with open(init, encoding="utf-8") as fh:
            text = fh.read(4000)
    except OSError:
        text = ""
    m = re.search(r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]', text, re.M)
    if m:
        ver = m.group(1)
    return ver, pkg


def engine_git_cwd() -> str | None:
    """Checkout to ask git about, or None when dc-engine is not a git tree."""
    root = dc_engine_source_root()
    if root and is_git_repo(root):
        return root
    try:
        pkg = dc_engine_package_dir()
    except SafetyError:
        return None
    if is_git_repo(pkg):
        try:
            return git_root(pkg)
        except GitError:
            return pkg
    return None


def capture_engine_pin() -> EnginePin:
    """Record installed dc-engine path plus git commit and `git diff` hash."""
    ver, path = dc_engine_meta()
    commit = None
    dirty = None
    cwd = engine_git_cwd()
    if cwd:
        commit = git_head(cwd)
        dirty = git_diff_hash(cwd)
    return EnginePin(
        git_commit=commit,
        git_dirty=dirty,
        package_path=path,
        version=ver,
    )


def ensure_engine_pin(expected: EnginePin) -> None:
    """Abort if dc-engine commit, dirty hash, or package path changed."""
    now = capture_engine_pin()
    if now.fingerprint() != expected.fingerprint():
        raise SafetyError(
            f"{ENGINE_CHANGED}: "
            f"was commit={expected.git_commit} dirty={expected.git_dirty} "
            f"path={expected.package_path}; "
            f"now commit={now.git_commit} dirty={now.git_dirty} "
            f"path={now.package_path}"
        )


def looks_like_dc_engine_tree(path: str) -> bool:
    """True when `path` looks like this project (src/dc_engine + src/dc_eval, or eval/ + dc_eval/)."""
    if not path or not os.path.isdir(path):
        return False
    if os.path.isdir(os.path.join(path, "src", "dc_engine")) and os.path.isdir(
        os.path.join(path, "src", "dc_eval")
    ):
        return True
    if os.path.isdir(os.path.join(path, "eval")) and os.path.isdir(os.path.join(path, "dc_eval")):
        return True
    return False


def refuse_task_repo(src_repo: str, task_id: str = "") -> None:
    """Task repos must never be (or contain, or live inside) the dc-engine source tree."""
    label = f"task {task_id!r}: " if task_id else ""
    root = dc_engine_source_root()
    if root and paths_overlap(src_repo, root):
        raise SafetyError(
            f"refusing {label}repo {src_repo} overlaps the dc-engine source tree "
            f"({root}). Point the task at a standalone fixture repo "
            "(see eval/fixtures/make_shop_repo.py)."
        )
    if looks_like_dc_engine_tree(src_repo):
        raise SafetyError(
            f"refusing {label}repo {src_repo} looks like the dc-engine source tree. "
            "Point the task at a standalone fixture repo."
        )


def run_copy_has_harness_dirs(repo_dir: str) -> list[str]:
    found: list[str] = []
    for rel in ("eval", "dc_eval", os.path.join("src", "dc_eval")):
        if os.path.isdir(os.path.join(repo_dir, rel)):
            found.append(rel.rstrip("/") + "/")
    return found


def refuse_run_copy(repo_dir: str) -> None:
    hits = run_copy_has_harness_dirs(repo_dir)
    if hits:
        raise SafetyError(
            f"refusing run copy {repo_dir}: contains {', '.join(hits)} "
            "(task repo must not be dc-engine)"
        )


def refuse_engine_inside_runs(eval_dir: str, engine_path: str) -> None:
    runs = os.path.join(os.path.abspath(eval_dir), "runs")
    if os.path.isdir(runs) and (
        realpath(engine_path) == realpath(runs)
        or realpath(engine_path).startswith(realpath(runs) + os.sep)
    ):
        raise SafetyError(
            f"dc-engine is loaded from {engine_path}, which is inside eval/runs/; refusing"
        )


def venv_bin_dir(venv: str) -> str:
    if os.name == "nt":
        return os.path.join(venv, "Scripts")
    return os.path.join(venv, "bin")


def venv_python(venv: str) -> str:
    bindir = venv_bin_dir(venv)
    for name in ("python", "python3", "python.exe"):
        path = os.path.join(bindir, name)
        if os.path.isfile(path):
            return path
    return os.path.join(bindir, "python")


def venv_env(venv: str, base: dict[str, str] | None = None) -> dict[str, str]:
    """PATH with the run venv first. Never the harness interpreter's pip."""
    env = dict(base or os.environ)
    bindir = venv_bin_dir(venv)
    env["VIRTUAL_ENV"] = venv
    env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    env.pop("PYTHONHOME", None)
    return env


def create_run_venv(slot: str) -> str:
    dest = os.path.join(slot, "venv")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(slot, exist_ok=True)
    r = subprocess.run(
        [sys.executable, "-m", "venv", dest],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"python -m venv failed ({r.returncode}): {dest}\n{r.stderr or r.stdout}"
        )
    return dest


def _hook_payload(command: str) -> str | None:
    cmd = (command or "").strip()
    if cmd.startswith("dc-engine "):
        return cmd[len("dc-engine "):]
    marker = " -m dc_engine "
    if marker in cmd:
        return cmd.split(marker, 1)[1]
    if cmd.startswith("dc-engine-mcp"):
        return None
    return None


def bind_cursor_interpreter(
    repo_dir: str,
    python: str | None = None,
    probe_python: str | None = None,
    *,
    tools: str | None = "slim",
    contract_policy: str | None = "required",
    write_mcp: bool = True,
) -> None:
    """Rewrite installer-written Cursor hooks/MCP to this interpreter."""
    py = os.path.abspath(python or sys.executable)
    hooks_path = os.path.join(repo_dir, ".cursor", "hooks.json")
    if os.path.isfile(hooks_path):
        with open(hooks_path, encoding="utf-8") as fh:
            data = json.load(fh)
        hooks = data.get("hooks")
        if isinstance(hooks, dict):
            for entries in hooks.values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    rest = _hook_payload(str(entry.get("command") or ""))
                    if rest is None:
                        continue
                    entry["command"] = hook_command(rest, py, probe_python)
            os.makedirs(os.path.dirname(hooks_path), exist_ok=True)
            tmp = hooks_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
            os.replace(tmp, hooks_path)
    mcp_path = os.path.join(repo_dir, ".cursor", "mcp.json")
    if write_mcp and (os.path.isfile(mcp_path) or tools):
        data: dict[str, Any] = {}
        if os.path.isfile(mcp_path):
            with open(mcp_path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data = loaded
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            servers = {}
            data["mcpServers"] = servers
        server: dict[str, Any] = {
            "command": py,
            "args": server_mcp_args(
                ".", tools=tools, contract_policy=contract_policy,
            ),
        }
        pp = (probe_python or "").strip()
        if pp:
            server["env"] = {"DC_PROBE_PYTHON": os.path.abspath(pp)}
        servers["dc-engine"] = server
        os.makedirs(os.path.dirname(mcp_path), exist_ok=True)
        tmp = mcp_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, mcp_path)


def apply_cursor_offline_policy(repo_dir: str) -> None:
    """Deny WebFetch in .cursor/cli.json and add an always-on offline rule.

    Merges with any cli.json the layer installer already wrote. Applied to
    both arms so baseline and layer are identical on web access.
    """
    cursor = os.path.join(repo_dir, ".cursor")
    os.makedirs(cursor, exist_ok=True)
    cli_path = os.path.join(cursor, "cli.json")
    data: dict[str, Any] = {}
    if os.path.isfile(cli_path):
        try:
            with open(cli_path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}
    perms = data.get("permissions")
    if not isinstance(perms, dict):
        perms = {}
        data["permissions"] = perms
    allow = perms.get("allow")
    if not isinstance(allow, list):
        allow = []
    deny = perms.get("deny")
    if not isinstance(deny, list):
        deny = []
    if WEBFETCH_DENY not in deny:
        deny.append(WEBFETCH_DENY)
    perms["allow"] = _dedupe_str(allow)
    perms["deny"] = _dedupe_str(deny)
    tmp = cli_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, cli_path)
    rules = os.path.join(cursor, "rules")
    os.makedirs(rules, exist_ok=True)
    rule_path = os.path.join(repo_dir, OFFLINE_RULE_REL)
    with open(rule_path, "w", encoding="utf-8") as fh:
        fh.write(OFFLINE_RULE)


def _dedupe_str(items: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        s = str(item)
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def cursor_preflight_argv(workspace: str, agent_bin: str = "agent") -> list[str]:
    """Validate project config without spending model tokens (`--list-models`)."""
    return [
        agent_bin,
        "--list-models",
        "--output-format", "stream-json",
        "--force", "--trust",
        "--workspace", workspace,
    ]


def preflight_cursor_cli(repo_dir: str, agent_bin: str = "agent") -> None:
    argv = cursor_preflight_argv(repo_dir, agent_bin=agent_bin)
    r = subprocess.run(
        argv, cwd=repo_dir, capture_output=True, text=True, timeout=60,
    )
    blob = ((r.stderr or "") + (r.stdout or "")).strip()
    if r.returncode != 0:
        raise SetupError(
            f"Cursor CLI preflight failed ({r.returncode}): {blob or 'no output'}"
        )


def slot_in_use(slot: str) -> bool:
    if not os.path.isdir(slot):
        return False
    if os.path.isdir(os.path.join(slot, "repo")):
        return True
    if os.path.isfile(os.path.join(slot, "metrics.json")):
        return True
    if os.path.isfile(os.path.join(slot, "stream.jsonl")):
        return True
    return False


def existing_run_slots(eval_dir: str, plan: list[tuple[Task, str, int]]) -> list[str]:
    out: list[str] = []
    for task, arm, rep in plan:
        slot = _run_dir(eval_dir, task.id, arm, rep)
        if slot_in_use(slot):
            out.append(slot)
    return out


def archive_run_dirs(eval_dir: str, slots: list[str]) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_root = os.path.join(eval_dir, "runs_archive", ts)
    runs_root = os.path.join(eval_dir, "runs")
    for slot in slots:
        if not os.path.isdir(slot):
            continue
        rel = os.path.relpath(slot, runs_root)
        dest = os.path.join(dest_root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(slot, dest)
    return dest_root


def append_result(path: str, row: dict[str, Any]) -> None:
    """Append a timestamped row. Never rewrite history."""
    item = dict(row)
    item.setdefault("recorded_at", utc_now_iso())
    _append_jsonl(path, item)


def _format_setup_exc(exc: BaseException) -> str:
    """Error message plus any captured subprocess output."""
    parts = [f"{type(exc).__name__}: {exc}"]
    for attr in ("stdout", "stderr", "output"):
        val = getattr(exc, attr, None)
        if val is None or val == b"" or val == "":
            continue
        if isinstance(val, bytes):
            val = val.decode("utf-8", errors="replace")
        parts.append(f"----- {attr} -----\n{val}")
    return "\n".join(parts)


def _append_setup_log(slot: str, title: str, text: str) -> None:
    os.makedirs(slot, exist_ok=True)
    path = os.path.join(slot, SETUP_LOG)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"===== {title} =====\n")
        fh.write(text if text.endswith("\n") else text + "\n")


def _setup_error_row(
    row: dict[str, Any],
    exc: BaseException,
    arm: str,
    log_text: str = "",
) -> dict[str, Any]:
    row["status"] = "setup_error"
    row["setup_error"] = f"{type(exc).__name__}: {exc}"
    row["resolved"] = False
    row.setdefault("regressions", None)
    row.setdefault("wall_time_s", 0)
    row.setdefault("agent_modified_hidden_test_files", [])
    if log_text:
        row["setup_log"] = log_text[-4000:]
    if not _arm_tracks_contracts(arm):
        row["contracts_created"] = 0
        row["final_contract_score"] = None
        row["stop_hook_blocks"] = 0
    return _apply_arm_meta(row, arm)


def _agent_error_row(row: dict[str, Any], reason: str) -> dict[str, Any]:
    row["status"] = "agent_error"
    row["agent_error"] = reason
    row["resolved"] = False
    row.setdefault("regressions", None)
    return row


def _merge_cursor_stream_extras(row: dict[str, Any], slot: str) -> None:
    """Refresh read_chars and web-call metrics from the saved stream."""
    path = os.path.join(slot, "stream.jsonl")
    if not os.path.isfile(path):
        return
    if row.get("runner") and row.get("runner") != "cursor":
        return
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return
    m = metrics_from_cursor_stream(text, wall_time_s=row.get("wall_time_s"))
    for k in (
        "read_chars",
        "web_search_count",
        "web_fetch_count",
        "web_call_count",
        "web_queries",
        "web_urls",
        "tool_result_chars",
        "tool_result_tokens",
        "tool_result_chars_total",
        "tool_result_tokens_total",
        "dc_engine_result_chars",
        "dc_engine_results",
        "dc_engine_largest",
        "model_requests",
        "tokens_per_request",
        "read_calls",
        "dc_engine_calls",
        "dc_engine_tool_calls",
        "dc_contract_calls",
    ):
        if k in m:
            row[k] = m[k]


def _mark_contaminated(row: dict[str, Any]) -> dict[str, Any]:
    search_n = int(row.get("web_search_count") or 0)
    fetch_n = int(row.get("web_fetch_count") or 0)
    row.setdefault("web_search_count", search_n)
    row.setdefault("web_fetch_count", fetch_n)
    row.setdefault("web_call_count", search_n + fetch_n)
    row.setdefault("web_queries", row.get("web_queries") or [])
    row.setdefault("web_urls", row.get("web_urls") or [])
    contaminated = (search_n + fetch_n) > 0
    row["contaminated"] = contaminated
    if (
        contaminated
        and row.get("status") not in ("grading_error", "setup_error", "agent_error")
        and not row.get("limited")
    ):
        row["status"] = "contaminated"
    return row


def plan_runs(
    tasks: list[Task],
    arms: tuple[str, ...] = ARMS,
    reps: int = DEFAULT_REPS,
    seed: int = DEFAULT_ARM_SEED,
) -> list[tuple[Task, str, int]]:
    """Interleave arms: for each task, for each rep, shuffle arm order (fixed seed)."""
    rng = random.Random(seed)
    plan: list[tuple[Task, str, int]] = []
    for task in tasks:
        for rep in range(1, reps + 1):
            order = list(arms)
            rng.shuffle(order)
            for arm in order:
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
    runner: str = "claude",
    seed: int = DEFAULT_ARM_SEED,
    arms: tuple[str, ...] | None = None,
) -> str:
    n = len(plan)
    typical, cap = estimate_cost(n, budget_usd)
    task_ids: list[str] = []
    arms_seen: list[str] = []
    for task, arm, _rep in plan:
        if task.id not in task_ids:
            task_ids.append(task.id)
        if arm not in arms_seen:
            arms_seen.append(arm)
    arm_label = ", ".join(arms) if arms else ", ".join(arms_seen)
    lines = [
        "tasks: " + (", ".join(task_ids) if task_ids else "(none)"),
        f"eval dir: {os.path.abspath(eval_dir)}",
        f"runner: {runner}",
        f"arms: {arm_label if arm_label else '(none)'}",
        f"arm order seed: {seed}  (shuffled within each task/rep)",
        f"runs: {n}  (interleaved arms, {timeout_s}s wall-clock timeout each)",
        f"model: {model}",
    ]
    if runner == "cursor":
        lines.append("one agent at a time (required so dashboard usage rows cannot overlap)")
        lines.append("cost: estimated from eval/prices.json (fill in real prices); not billed")
        lines.append("turn off on-demand spending in the Cursor dashboard before a live run")
    else:
        lines.append(f"budget cap: ${budget_usd:.2f} / run  (hard cap ${cap:.2f} via --max-budget-usd)")
        lines.append(f"rough cost estimate: ${typical:.2f}–${cap:.2f}  (highly variable; not a quote)")
    lines.append("isolated venv per run (setup, grading, and the agent's PATH; never the harness pip)")
    lines += ["", "order:"]
    for i, (task, arm, rep) in enumerate(plan, 1):
        lines.append(f"  {i:3d}. {task.id}  {arm:8s}  rep {rep}  base={task.commit[:10]}")
        if runner == "cursor":
            repo_copy = os.path.join(_run_dir(os.path.abspath(eval_dir), task.id, arm, rep), "repo")
            try:
                argv = cursor_argv(task.prompt, model=model, workspace=repo_copy)
            except ValueError as exc:
                raise SafetyError(str(exc)) from exc
            lines.append(f"       command: {_fmt_cmd(argv)}")
            lines.append(f"       {arm_extras_note(arm)}")
    return "\n".join(lines)


def _fmt_cmd(argv: list[str]) -> str:
    parts = []
    for a in argv:
        if any(ch in a for ch in (' ', "'", '"', "\n")):
            parts.append("'" + a.replace("'", "'\\''") + "'")
        else:
            parts.append(a)
    return " ".join(parts)


def _run_dir(eval_dir: str, task_id: str, arm: str, rep: int) -> str:
    return os.path.join(eval_dir, "runs", task_id, arm, str(rep))


def utc_now_iso() -> str:
    """Millisecond UTC timestamp, e.g. 2026-10-14T13:05:01.123Z."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(now.microsecond / 1000):03d}Z"


def has_cursor_auth() -> bool:
    """True if CURSOR_API_KEY is set or a local CLI login file exists.

    Never reads or returns key material.
    """
    if os.environ.get("CURSOR_API_KEY"):
        return True
    for p in (
        os.path.expanduser("~/.cursor/cli-config.json"),
        os.path.expanduser("~/.cursor/auth.json"),
        os.path.expanduser("~/.config/cursor/auth.json"),
    ):
        if os.path.isfile(p):
            return True
    return False


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


def _require_cursor(bin_name: str) -> str:
    if not has_cursor_auth():
        raise SafetyError(
            "Cursor CLI is not authenticated. Log in with the Cursor CLI, or set "
            "CURSOR_API_KEY in the environment (the harness never prints or stores it)."
        )
    path = shutil.which(bin_name)
    if not path:
        raise SafetyError(
            f"Cursor CLI not found ({bin_name!r}). Install it (https://cursor.com/docs/cli/headless) "
            "and ensure `agent` is on PATH. Tests never call the real CLI."
        )
    return path


def _agent_version(bin_name: str) -> str | None:
    """`agent --version` for run metadata. Never used by unit tests."""
    try:
        r = subprocess.run(
            [bin_name, "--version"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (r.stdout or r.stderr or "").strip()
    return text or None


def _install_cursor_layer(
    repo_dir: str,
    python: str | None = None,
    probe_python: str | None = None,
    arm: str = "layer",
) -> None:
    cfg = arm_config(arm)
    write_layer_repo_config(repo_dir)
    py = os.path.abspath(python or sys.executable)
    cmd = [py, "-m", "dc_engine", "--root", repo_dir, "install", "--cursor"]
    tools = cfg.get("tools") or "slim"
    if tools != "slim":
        cmd.extend(["--tools", str(tools)])
    env = os.environ.copy()
    src = harness_src_dir()
    cur = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + cur if cur else "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(
            f"dc-engine install --cursor failed ({r.returncode}): {r.stderr or r.stdout}"
        )
    bind_cursor_interpreter(
        repo_dir, py, probe_python,
        tools=tools,
        contract_policy=cfg.get("contract_policy") or "required",
    )


def _run_complete(slot: str) -> bool:
    path = os.path.join(slot, "metrics.json")
    return os.path.isfile(path)


def _load_metrics(slot: str) -> dict[str, Any] | None:
    path = os.path.join(slot, "metrics.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_metrics(slot: str, row: dict[str, Any]) -> None:
    os.makedirs(slot, exist_ok=True)
    with open(os.path.join(slot, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(row, fh, indent=2)
        fh.write("\n")


def agent_finished(slot: str) -> bool:
    """True when a previous agent attempt is complete enough to skip on --resume."""
    metrics = _load_metrics(slot)
    stream = os.path.join(slot, "stream.jsonl")
    stream_n = os.path.getsize(stream) if os.path.isfile(stream) else 0
    if metrics is None:
        return stream_n > 0
    st = metrics.get("status")
    if st == "setup_error":
        return False
    if st == "grading_error":
        return True
    if st == "agent_error":
        return True
    rc = metrics.get("returncode")
    if stream_n == 0 and rc not in (0, None):
        return False
    return True


def needs_regrade(slot: str) -> bool:
    metrics = _load_metrics(slot)
    if metrics is None:
        return agent_finished(slot)
    return metrics.get("status") == "grading_error"


def _hooks_log_text(repo_dir: str) -> str:
    path = os.path.join(repo_dir, ".dc-engine", "hooks.log")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _append_jsonl(path: str, row: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def upsert_result(path: str, row: dict[str, Any]) -> None:
    """Replace the last matching task/arm/rep row, or append."""
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
    key = (str(row.get("task")), str(row.get("arm")), str(row.get("rep")))
    replaced = False
    out: list[dict[str, Any]] = []
    for existing in rows:
        ek = (str(existing.get("task")), str(existing.get("arm")), str(existing.get("rep")))
        if ek == key:
            if not replaced:
                out.append(row)
                replaced = True
            continue
        out.append(existing)
    if not replaced:
        out.append(row)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for item in out:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def _apply_grade(row: dict[str, Any], grade: dict[str, Any], arm: str) -> dict[str, Any]:
    row["resolved"] = grade.get("resolved")
    row["regressions"] = grade.get("regressions")
    row["hidden"] = grade.get("hidden")
    row["regression"] = grade.get("regression")
    row["modified_tests"] = grade.get("modified_tests")
    row["diff_size"] = grade.get("diff_size")
    row["agent_modified_hidden_test_files"] = grade.get("agent_modified_hidden_test_files") or []
    row["contracts_created"] = (
        grade.get("contracts_created") if _arm_tracks_contracts(arm) else 0
    )
    row["final_contract_score"] = (
        grade.get("final_contract_score") if _arm_tracks_contracts(arm) else None
    )
    if _arm_tracks_contracts(arm):
        stop_blocks = max(
            int(row.get("stop_hook_blocks_stream") or 0),
            int(grade.get("stop_hook_blocks_disk") or 0),
        )
        row["stop_hook_blocks"] = stop_blocks
    else:
        row["stop_hook_blocks"] = 0
    return row


def _grade_error_row(row: dict[str, Any], exc: BaseException, arm: str) -> dict[str, Any]:
    row["status"] = "grading_error"
    row["grading_error"] = f"{type(exc).__name__}: {exc}"
    row["resolved"] = False
    row.setdefault("regressions", None)
    row.setdefault("agent_modified_hidden_test_files", [])
    if not _arm_tracks_contracts(arm):
        row["contracts_created"] = 0
        row["final_contract_score"] = None
        row["stop_hook_blocks"] = 0
    return row


def regrade_slot(
    task: Task,
    slot: str,
    *,
    src_repo: str,
    python: str | None = None,
) -> dict[str, Any]:
    """Re-run grading on a saved run copy. Never launches an agent."""
    repo_dir = os.path.join(slot, "repo")
    if not os.path.isdir(repo_dir):
        raise RuntimeError(f"no saved repo copy at {repo_dir}")
    row = _load_metrics(slot) or {
        "task": task.id,
        "arm": os.path.basename(os.path.dirname(slot)),
        "rep": int(os.path.basename(slot) or 0),
        "run_dir": slot,
        "commit": task.commit,
        "repo": src_repo,
    }
    arm = str(row.get("arm") or os.path.basename(os.path.dirname(slot)))
    _merge_cursor_stream_extras(row, slot)
    py = python
    venv = os.path.join(slot, "venv")
    if py is None and os.path.isdir(venv):
        py = venv_python(venv)
    try:
        if py and os.path.isdir(venv):
            install_test_env(py, repo_dir, env=venv_env(venv))
        grade = grade_repo(
            task, repo_dir, python=py, src_repo=src_repo, run_dir=slot,
        )
        row = _apply_grade(row, grade, arm)
        row["status"] = "ok"
        row.pop("grading_error", None)
    except Exception as exc:
        row = _grade_error_row(row, exc, arm)
    row = _mark_contaminated(row)
    row["run_dir"] = slot
    _write_metrics(slot, row)
    return row


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
    runner: str = "claude",
    agent_bin: str = "agent",
    reuse: bool = False,
    do_grade: bool = True,
    engine_pin: EnginePin | None = None,
) -> dict[str, Any]:
    slot = _run_dir(eval_dir, task.id, arm, rep)
    if slot_in_use(slot) and not reuse:
        raise SafetyError(
            f"run directory already exists: {slot}. "
            "Pass --fresh to archive it, or --resume to skip finished runs."
        )
    repo_dir = os.path.join(slot, "repo")
    pin = engine_pin or capture_engine_pin()
    engine_ver, engine_path = pin.version, pin.package_path
    py = None
    venv = None
    argv: list[str] = []
    run_env: dict[str, str] | None = None
    agent_ver = None
    mcp_path = settings_path = None
    cfg = arm_config(arm)
    try:
        if repo_is_working_copy(repo_dir):
            raise SafetyError(f"refusing to run in the working copy: {repo_dir}")
        if realpath(repo_dir) == realpath(os.getcwd()):
            raise SafetyError("run directory resolved to the current working directory")
        refuse_task_repo(src_repo, task.id)
        _fresh_copy(src_repo, task.commit, repo_dir)
        if repo_is_working_copy(repo_dir) or realpath(repo_dir) == realpath(src_repo):
            shutil.rmtree(repo_dir, ignore_errors=True)
            raise SafetyError(
                "refusing to run in the working copy; the isolated checkout resolved "
                f"to {repo_dir}"
            )
        refuse_run_copy(repo_dir)
        refuse_engine_inside_runs(eval_dir, engine_path)
        if do_grade:
            venv = create_run_venv(slot)
            run_env = venv_env(venv)
            py = venv_python(venv)
            install_test_env(py, repo_dir, env=run_env)
            run_setup(repo_dir, task.setup, env=run_env)
            probe_py = py if cfg["mcp"] else None
        else:
            py = sys.executable
            probe_py = py if cfg["mcp"] else None
            if task.setup:
                run_setup(repo_dir, task.setup, env=run_env)
        if runner == "cursor":
            argv = cursor_argv(
                task.prompt, model=model, workspace=repo_dir, agent_bin=agent_bin,
            )
            if cfg["mcp"] and cfg["hooks"]:
                _install_cursor_layer(repo_dir, probe_python=probe_py, arm=arm)
            elif cfg["mcp"]:
                bind_cursor_interpreter(
                    repo_dir, probe_python=probe_py,
                    tools=cfg.get("tools"),
                    contract_policy=cfg.get("contract_policy"),
                    write_mcp=True,
                )
            apply_cursor_offline_policy(repo_dir)
            preflight_cursor_cli(repo_dir, agent_bin=agent_bin)
            agent_ver = _agent_version(agent_bin)
        else:
            if cfg["mcp"]:
                mcp_path, settings_path = write_layer_files(
                    slot, probe_python=probe_py,
                    tools=cfg.get("tools"),
                    contract_policy=cfg.get("contract_policy"),
                    hooks=bool(cfg["hooks"]),
                )
                if cfg["hooks"]:
                    write_layer_repo_config(repo_dir)
            argv = claude_argv(
                task.prompt, arm,
                model=model, budget_usd=budget_usd,
                mcp_config=mcp_path, settings=settings_path,
                claude_bin=claude_bin,
            )
    except SafetyError:
        raise
    except Exception as exc:
        log = _format_setup_exc(exc)
        _append_setup_log(slot, "setup", log)
        row = {
            "task": task.id, "arm": arm, "rep": rep, "runner": runner,
            "model": model, "run_dir": slot, "repo": src_repo,
            "commit": task.commit, "resolved": False,
            **pin.as_metrics(),
        }
        row = _setup_error_row(row, exc, arm, log)
        _write_metrics(slot, row)
        return row
    with open(os.path.join(slot, "command.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "argv": argv,
            "cwd": repo_dir,
            "agent_version": agent_ver,
            "dc_engine_version": engine_ver,
            "dc_engine_path": engine_path,
            "dc_engine_git_commit": pin.git_commit,
            "dc_engine_git_dirty": pin.git_dirty,
            "venv": venv,
        }, fh, indent=2)
        fh.write("\n")
    stream_path = os.path.join(slot, "stream.jsonl")
    stderr_path = os.path.join(slot, "stderr.txt")
    started_at = utc_now_iso()
    t0 = time.monotonic()
    timed_out = False
    returncode = -1
    try:
        with open(stream_path, "w", encoding="utf-8") as out, open(
            stderr_path, "w", encoding="utf-8"
        ) as err:
            proc = subprocess.run(
                argv, cwd=repo_dir, stdout=out, stderr=err,
                timeout=timeout_s, env=run_env,
            )
            returncode = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        returncode = -9
    wall = time.monotonic() - t0
    ended_at = utc_now_iso()
    stream_text = ""
    if os.path.isfile(stream_path):
        with open(stream_path, encoding="utf-8") as fh:
            stream_text = fh.read()
    stderr_text = ""
    if os.path.isfile(stderr_path):
        with open(stderr_path, encoding="utf-8") as fh:
            stderr_text = fh.read()
    limited = runner == "cursor" and is_limit_error(stderr_text, stream_text)
    if runner == "cursor":
        metrics = metrics_from_cursor_stream(stream_text, wall_time_s=wall)
        est = estimate_cost_usd(
            model=model,
            input_tokens=metrics.get("input_tokens"),
            output_tokens=metrics.get("output_tokens"),
            cache_read_tokens=metrics.get("cache_read_tokens"),
            cache_write_tokens=metrics.get("cache_write_tokens"),
            eval_dir=eval_dir,
        )
        metrics["cost_usd"] = est
        metrics["cost_estimated"] = True
        log_text = _hooks_log_text(repo_dir)
        hook_sum = summarize_hooks_log(log_text)
        if cfg["hooks"]:
            metrics["hooks_active"] = bool(hook_sum.get("hooks_active"))
            metrics["hook_calls"] = hook_sum.get("hook_calls") or 0
            metrics["hook_calls_by_event"] = hook_sum.get("hook_calls_by_event") or {}
            metrics["hook_denials"] = hook_sum.get("hook_denials") or 0
            metrics["hook_stop_followups"] = hook_sum.get("hook_stop_followups") or 0
            metrics["hook_errors"] = hook_sum.get("hook_errors") or 0
            metrics["hook_log_effects"] = (
                int(hook_sum.get("hook_calls") or 0) - int(hook_sum.get("hook_errors") or 0)
            )
        else:
            metrics["hooks_active"] = False
            metrics["hook_calls"] = 0
            metrics["hook_calls_by_event"] = {}
            metrics["hook_denials"] = 0
            metrics["hook_stop_followups"] = 0
            metrics["hook_errors"] = 0
            metrics["hook_log_effects"] = 0
    else:
        metrics = metrics_from_stream(stream_text, wall_time_s=wall)
        metrics["hooks_active"] = None
        metrics["cost_estimated"] = False
    row: dict[str, Any] = {
        "task": task.id,
        "arm": arm,
        "rep": rep,
        "runner": runner,
        "model": model,
        "agent_version": agent_ver,
        **pin.as_metrics(),
        "commit": task.commit,
        "repo": src_repo,
        "run_dir": slot,
        "started_at": started_at,
        "ended_at": ended_at,
        "returncode": returncode,
        "timed_out": timed_out,
        "limited": limited,
        **metrics,
        "checkpoints_restored": (
            metrics.get("checkpoints_restored") if cfg["hooks"] else 0
        ),
    }
    row = _apply_arm_meta(row, arm, metrics)
    has_result = stream_has_result(stream_text)
    agent_failed = (not limited) and (returncode != 0 or not has_result)
    if agent_failed:
        reason = (stderr_text or "").strip()
        if timed_out:
            reason = ("timed out. " + reason).strip()
        if not reason:
            reason = (
                f"agent exit {returncode} with no result event in the stream"
            )
        row = _agent_error_row(row, reason[:4000])
        row = _mark_contaminated(row)
        _write_metrics(slot, row)
        return row
    if not do_grade:
        row["status"] = "ok"
        row["resolved"] = None
        row = _mark_contaminated(row)
        _write_metrics(slot, row)
        return row
    try:
        grade = grade_repo(
            task, repo_dir, python=py,
            src_repo=src_repo, run_dir=slot,
        )
        row = _apply_grade(row, grade, arm)
        row["status"] = "ok"
        row.pop("grading_error", None)
    except Exception as exc:
        row = _grade_error_row(row, exc, arm)
    row = _mark_contaminated(row)
    _write_metrics(slot, row)
    return row


def run_eval(
    eval_dir: str,
    *,
    task_ids: list[str] | None = None,
    exclude_ids: list[str] | None = None,
    arms: tuple[str, ...] = ARMS,
    reps: int = DEFAULT_REPS,
    dry_run: bool = False,
    model: str = DEFAULT_MODEL,
    budget_usd: float = DEFAULT_BUDGET_USD,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    claude_bin: str = "claude",
    runner: str = "claude",
    resume: bool = False,
    fresh: bool = False,
    agent_bin: str = "agent",
    seed: int = DEFAULT_ARM_SEED,
) -> int:
    print_safety_warning()
    eval_dir = os.path.abspath(eval_dir)
    runner = (runner or "claude").strip().lower()
    if runner not in ("claude", "cursor"):
        raise SafetyError(f"unknown runner {runner!r} (use claude or cursor)")
    if runner == "cursor":
        m = (model or "").strip()
        if not m or m.lower() == "auto":
            raise SafetyError(
                'refusing model "auto" (or empty). Pass a fixed --model so both arms match.'
            )
        ensure_prices_file(eval_dir)
    loaded = load_tasks(eval_dir)
    if not loaded:
        print(f"no tasks in {os.path.join(eval_dir, 'tasks')}", file=sys.stderr)
        return 1
    tasks = select_tasks(loaded, include=task_ids, exclude=exclude_ids)
    if not tasks:
        print("no tasks selected", file=sys.stderr)
        return 1
    for task in tasks:
        src = resolve_repo(task, eval_dir)
        refuse_task_repo(src, task.id)
        if repo_is_working_copy(src):
            raise SafetyError(
                f"refusing to run: task {task.id!r} repo is the current working copy "
                f"({src}). Run dc-eval from another directory, or point the task at a clone."
            )
    plan = plan_runs(tasks, arms=arms, reps=reps, seed=seed)
    print(format_plan(
        plan, model=model, budget_usd=budget_usd, timeout_s=timeout_s,
        eval_dir=eval_dir, runner=runner, seed=seed, arms=arms,
    ))
    pin = capture_engine_pin()
    print(format_engine_pin(pin), flush=True)
    existing = existing_run_slots(eval_dir, plan)
    if existing and not resume and not fresh:
        shown = "\n".join("  " + s for s in existing[:12])
        extra = f"\n  ... and {len(existing) - 12} more" if len(existing) > 12 else ""
        n = len(existing)
        label = (
            "run directory already exists" if n == 1
            else "run directories already exist"
        )
        raise SafetyError(
            f"{n} {label}. "
            "Pass --fresh to archive them under eval/runs_archive/<timestamp>/, "
            "or --resume to skip finished agents.\n" + shown + extra
        )
    if dry_run:
        if fresh and existing:
            print(f"dry-run: --fresh would archive {len(existing)} run dir(s)", flush=True)
        return 0
    if fresh and existing:
        dest = archive_run_dirs(eval_dir, existing)
        print(f"archived {len(existing)} run dir(s) to {dest}", flush=True)
    claude_path = claude_bin
    agent_path = agent_bin
    if runner == "cursor":
        agent_path = _require_cursor(agent_bin)
    else:
        _require_api_key()
        claude_path = _require_claude(claude_bin)
    results_path = os.path.join(eval_dir, "results.jsonl")
    n_ok = 0
    skipped = 0
    regraded = 0
    grade_errors = 0
    consecutive_setup = 0
    for task, arm, rep in plan:
        slot = _run_dir(eval_dir, task.id, arm, rep)
        src = resolve_repo(task, eval_dir)
        if resume and agent_finished(slot):
            if needs_regrade(slot):
                print(f"\nregrade {task.id} {arm} rep {rep} (agent finished, grading_error)", flush=True)
                try:
                    row = regrade_slot(task, slot, src_repo=src)
                except Exception as exc:
                    row = _grade_error_row(
                        {"task": task.id, "arm": arm, "rep": rep, "run_dir": slot},
                        exc, arm,
                    )
                    _write_metrics(slot, row)
                append_result(results_path, row)
                regraded += 1
                if row.get("status") == "grading_error":
                    grade_errors += 1
                    print(f"  GRADING_ERROR  {row.get('grading_error')}", flush=True)
                elif row.get("status") == "contaminated" or row.get("contaminated"):
                    print(
                        f"  CONTAMINATED  web={row.get('web_call_count') or 0}  "
                        f"(regraded)",
                        flush=True,
                    )
                else:
                    flag = "RESOLVED" if row.get("resolved") else "unresolved"
                    print(f"  {flag}  (regraded)", flush=True)
            else:
                print(f"\nskip {task.id} {arm} rep {rep} (already complete)", flush=True)
                skipped += 1
            continue
        print(f"\n→ {task.id} {arm} rep {rep}", flush=True)
        ensure_engine_pin(pin)
        try:
            row = execute_run(
                task, arm, rep,
                eval_dir=eval_dir, model=model, budget_usd=budget_usd,
                timeout_s=timeout_s, claude_bin=claude_path, src_repo=src,
                runner=runner, agent_bin=agent_path, reuse=resume,
                engine_pin=pin,
            )
        except SafetyError:
            raise
        except Exception as exc:
            row = _grade_error_row(
                {
                    "task": task.id, "arm": arm, "rep": rep, "run_dir": slot,
                    "repo": src, **pin.as_metrics(),
                },
                exc, arm,
            )
            _write_metrics(slot, row)
        append_result(results_path, row)
        n_ok += 1
        if row.get("limited"):
            print(
                "LIMITED: this run hit a Cursor plan/usage limit and is excluded from metrics.\n"
                "Turn off on-demand spending only after the batch; wait until usage resets, then:\n"
                f"  dc-eval run --runner cursor --resume --model {model} --eval-dir {eval_dir}",
                flush=True,
            )
            return 3
        if row.get("status") == "setup_error":
            consecutive_setup += 1
            err = str(row.get("setup_error") or "")
            print(f"  SETUP_ERROR  {err}", flush=True)
            if consecutive_setup >= CONSECUTIVE_SETUP_STOP:
                print(
                    f"\nstopping after {consecutive_setup} consecutive setup_error runs:\n{err}",
                    flush=True,
                )
                return 4
            continue
        consecutive_setup = 0
        if row.get("status") == "agent_error":
            print(f"  AGENT_ERROR  {row.get('agent_error')}", flush=True)
            continue
        if row.get("status") == "grading_error":
            grade_errors += 1
            print(f"  GRADING_ERROR  {row.get('grading_error')}", flush=True)
            continue
        if row.get("status") == "contaminated" or row.get("contaminated"):
            print(
                f"  CONTAMINATED  web={row.get('web_call_count') or 0}  "
                f"time={row.get('wall_time_s', 0):.0f}s",
                flush=True,
            )
            continue
        flag = "RESOLVED" if row.get("resolved") else "unresolved"
        cost = row.get("cost_usd")
        est = " estimated" if row.get("cost_estimated") else ""
        cost_s = f"${cost:.4f}{est}" if isinstance(cost, (int, float)) else "n/a"
        extra = ""
        if runner == "cursor":
            extra = f"  hooks active: {'yes' if row.get('hooks_active') else 'no'}"
        print(f"  {flag}  cost={cost_s}  time={row.get('wall_time_s', 0):.0f}s{extra}")
    bits = [f"wrote {n_ok} rows to {results_path}"]
    if skipped:
        bits.append(f"skipped {skipped}")
    if regraded:
        bits.append(f"regraded {regraded}")
    if grade_errors:
        bits.append(f"grading_error {grade_errors}")
    print("\n" + "  ".join(bits))
    return 0


def grade_runs(
    eval_dir: str,
    *,
    task_ids: list[str] | None = None,
    exclude_ids: list[str] | None = None,
) -> int:
    """Re-grade saved run copies. Never launches an agent."""
    eval_dir = os.path.abspath(eval_dir)
    loaded = load_tasks(eval_dir)
    if not loaded:
        print(f"no tasks in {os.path.join(eval_dir, 'tasks')}", file=sys.stderr)
        return 1
    tasks = select_tasks(loaded, include=task_ids, exclude=exclude_ids)
    if not tasks:
        print("no tasks selected", file=sys.stderr)
        return 1
    results_path = os.path.join(eval_dir, "results.jsonl")
    n = 0
    errors = 0
    for task in tasks:
        task_root = os.path.join(eval_dir, "runs", task.id)
        if not os.path.isdir(task_root):
            continue
        src = resolve_repo(task, eval_dir)
        for arm in sorted(os.listdir(task_root)):
            arm_dir = os.path.join(task_root, arm)
            if not os.path.isdir(arm_dir):
                continue
            for name in sorted(os.listdir(arm_dir)):
                slot = os.path.join(arm_dir, name)
                repo_dir = os.path.join(slot, "repo")
                if not os.path.isdir(repo_dir):
                    continue
                print(f"grade {task.id} {arm} {name}", flush=True)
                try:
                    row = regrade_slot(task, slot, src_repo=src)
                except Exception as exc:
                    row = _grade_error_row(
                        {"task": task.id, "arm": arm, "rep": name, "run_dir": slot},
                        exc, arm,
                    )
                    _write_metrics(slot, row)
                append_result(results_path, row)
                n += 1
                if row.get("status") == "grading_error":
                    errors += 1
                    print(f"  GRADING_ERROR  {row.get('grading_error')}", flush=True)
                elif row.get("status") == "contaminated" or row.get("contaminated"):
                    print(
                        f"  CONTAMINATED  web={row.get('web_call_count') or 0}  "
                        f"resolved={bool(row.get('resolved'))}  "
                        f"regressions={row.get('regressions')}",
                        flush=True,
                    )
                else:
                    flag = "RESOLVED" if row.get("resolved") else "unresolved"
                    print(f"  {flag}", flush=True)
    print(f"\nregraded {n} runs" + (f"  grading_error {errors}" if errors else ""))
    return 0
