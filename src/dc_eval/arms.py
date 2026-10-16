"""Claude Code / Cursor CLI invocations for eval arms.

Flags match https://code.claude.com/docs/en/cli-reference and
https://code.claude.com/docs/en/headless — `claude --bare -p`,
`--output-format stream-json --verbose`, `--permission-mode acceptEdits`,
`--allowedTools`, `--max-budget-usd`, plus `--mcp-config` / `--settings`
on MCP arms.
"""

from __future__ import annotations

import json
import os
import shutil
import shlex
import sys
from typing import Any

from . import ALL_ARMS, ARMS

# Per-arm recipe: MCP tool surface, contract policy, and whether hooks run.
# Cursor argv is identical; only files in the run copy differ.
ARM_CONFIG: dict[str, dict[str, Any]] = {
    "baseline": {
        "mcp": False, "hooks": False, "tools": None,
        "contract_policy": None, "hook_mode": "off",
    },
    "tools": {
        "mcp": True, "hooks": False, "tools": "slim",
        "contract_policy": "optional", "hook_mode": "off",
    },
    "contracts": {
        "mcp": True, "hooks": True, "tools": "contracts",
        "contract_policy": "required", "hook_mode": "block",
    },
    "layer": {
        "mcp": True, "hooks": True, "tools": "slim",
        "contract_policy": "required", "hook_mode": "block",
    },
    # Trajectory-mined checks (dc_engine/proviso.py): Claude Code hooks only, no MCP tools.
    "proviso": {
        "mcp": False, "hooks": False, "tools": None, "contract_policy": None, "hook_mode": "proviso",
        "proviso": {"context": True, "trajectory": True, "tests": True},
    },
    "replay-only": {
        "mcp": False, "hooks": False, "tools": None, "contract_policy": None, "hook_mode": "proviso",
        "proviso": {"context": False, "trajectory": True, "tests": True},
    },
    "tests-only": {
        "mcp": False, "hooks": False, "tools": None, "contract_policy": None, "hook_mode": "proviso",
        "proviso": {"context": False, "trajectory": False, "tests": True},
    },
    # Pre-fetch ceiling: a per-task brief (eval_dir/briefs/<task id>.md) built from what baseline
    # agents read before their first edit, pushed at prompt time. No replay, no test check.
    # Change impact: broad test runs rewritten to affected tests (PreToolUse) + ripple replay at Stop.
    # Assets per task in eval_dir/impact/<task id>/ (covmap, base failures, probes, base outputs, replay runner).
    "impact": {
        "mcp": False, "hooks": False, "tools": None, "contract_policy": None, "hook_mode": "proviso",
        "proviso": {"context": False, "trajectory": False, "tests": False, "impact": True, "ripple": True},
    },
    "intercept-only": {
        "mcp": False, "hooks": False, "tools": None, "contract_policy": None, "hook_mode": "proviso",
        "proviso": {"context": False, "trajectory": False, "tests": False, "impact": True, "ripple": False},
    },
    "oracle": {
        "mcp": False, "hooks": False, "tools": None, "contract_policy": None, "hook_mode": "proviso",
        "proviso": {"context": False, "trajectory": False, "tests": False, "brief": True},
    },
}

# Built-in tools the agent needs to read, edit, and run pytest (headless docs).
# Layer arm also allows the dc-engine MCP server (prefix form from the CLI ref).
BASELINE_TOOLS = "Bash,Read,Edit,Write,MultiEdit,Glob,Grep"
LAYER_TOOLS = BASELINE_TOOLS + ",mcp__dc-engine"

PRE_MATCHER = (
    "Bash|Edit|Write|MultiEdit|"
    "mcp__dc-engine__dc_replace_symbol|mcp__dc-engine__dc_insert_symbol"
)
POST_MATCHER = "Edit|Write|MultiEdit"
HOOK_PRE = "dc-engine hook pre-edit"
HOOK_POST = "dc-engine hook post-edit"
HOOK_STOP = "dc-engine hook stop"


def parse_arms(spec: str | None, arm_flag: str | None = None) -> tuple[str, ...]:
    """Parse `--arms a,b` (preferred) or legacy `--arm both|name`."""
    if spec and str(spec).strip():
        parts = [p.strip().lower() for p in str(spec).split(",") if p.strip()]
        if not parts:
            raise ValueError("--arms is empty")
        seen: set[str] = set()
        out: list[str] = []
        for p in parts:
            if p not in ARM_CONFIG:
                raise ValueError(
                    f"unknown arm {p!r}; use {', '.join(ALL_ARMS)}"
                )
            if p in seen:
                raise ValueError(f"duplicate arm {p!r} in --arms")
            seen.add(p)
            out.append(p)
        return tuple(out)
    if arm_flag and arm_flag != "both":
        a = arm_flag.strip().lower()
        if a not in ARM_CONFIG:
            raise ValueError(f"unknown arm {a!r}; use {', '.join(ALL_ARMS)}")
        return (a,)
    return ARMS


def arm_config(arm: str) -> dict[str, Any]:
    a = (arm or "").strip().lower()
    if a not in ARM_CONFIG:
        raise ValueError(f"unknown arm: {arm}")
    return ARM_CONFIG[a]


def arm_extras_note(arm: str) -> str:
    """One-line dry-run description of MCP/hooks for this arm."""
    cfg = arm_config(arm)
    if not cfg["mcp"]:
        return "layer extras: none (no dc-engine MCP, no dc-engine hooks)"
    flags: list[str] = []
    if cfg["tools"] and cfg["tools"] != "slim":
        flags.append(f"--tools {cfg['tools']}")
    if cfg["contract_policy"] == "optional":
        flags.append("--contracts optional")
    flag_s = (" " + " ".join(flags)) if flags else ""
    if cfg["hooks"]:
        inst = engine_cli_cmd(f"--root <run-copy> install --cursor{flag_s}")
        if cfg["tools"] == "contracts":
            detail = (
                "hooks + dc_contract/dc_replace_symbol only; "
                "commands use this interpreter"
            )
        else:
            detail = "hooks + MCP in the copy only; commands use this interpreter"
        return f"layer extras: `{inst}` ({detail})"
    return (
        "layer extras: slim MCP, no hooks "
        "(contracts optional; dc_contract available but never required)"
    )


def server_mcp_args(
    root: str = ".",
    *,
    tools: str | None = "slim",
    contract_policy: str | None = "required",
) -> list[str]:
    args = ["-m", "dc_engine.server", "--root", root]
    t = (tools or "slim").strip().lower()
    if t and t != "slim":
        args.extend(["--tools", t])
    pol = (contract_policy or "required").strip().lower()
    if pol == "optional":
        args.extend(["--contracts", "optional"])
    return args


def harness_python() -> str:
    return os.path.abspath(sys.executable)


def engine_cli_cmd(args: str, python: str | None = None) -> str:
    """Shell command that runs this harness's dc-engine, never PATH `dc-engine`."""
    py = os.path.abspath(python or sys.executable)
    return f"{shlex.quote(py)} -m dc_engine {args}"


def hook_command(
    args: str,
    python: str | None = None,
    probe_python: str | None = None,
) -> str:
    """Hook shell command, with DC_PROBE_PYTHON set when the run has a venv."""
    cmd = engine_cli_cmd(args, python)
    pp = (probe_python or "").strip()
    if not pp:
        return cmd
    return f"DC_PROBE_PYTHON={shlex.quote(os.path.abspath(pp))} {cmd}"


def layer_settings(
    python: str | None = None,
    probe_python: str | None = None,
) -> dict[str, Any]:
    """Hooks with enforce=block, same matcher groups as `dc-engine install`."""
    def group(command: str, matcher: str | None = None) -> dict[str, Any]:
        g: dict[str, Any] = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            g["matcher"] = matcher
        return g
    return {
        "hooks": {
            "PreToolUse": [group(hook_command("hook pre-edit", python, probe_python), PRE_MATCHER)],
            "PostToolUse": [group(hook_command("hook post-edit", python, probe_python), POST_MATCHER)],
            "Stop": [group(hook_command("hook stop", python, probe_python))],
        }
    }


def proviso_settings(python: str | None = None, probe_python: str | None = None,
                     flags: dict[str, Any] | None = None) -> dict[str, Any]:
    """Claude Code hooks for the proviso arms (prompt context, Bash capture, Stop verify).

    Arms with neither trajectory replay nor test checks (the pre-fetch arms) get only the prompt hook.
    """
    def group(args: str, matcher: str | None = None, timeout: int = 120) -> dict[str, Any]:
        g: dict[str, Any] = {"hooks": [{"type": "command",
                                        "command": hook_command(args, python, probe_python),
                                        "timeout": timeout}]}
        if matcher:
            g["matcher"] = matcher
        return g
    flags = flags or None
    prompt_hooks = [group("hook proviso-context")]
    if flags and flags.get("brief"):
        from dc_engine.proviso import BRIEF_PARTS
        prompt_hooks += [group(f"hook proviso-brief-{i}") for i in range(1, BRIEF_PARTS + 1)]
    hooks: dict[str, Any] = {"UserPromptSubmit": prompt_hooks}
    if flags is None or flags.get("trajectory"):
        hooks["PostToolUse"] = [group("hook proviso-capture", "Bash")]
    if flags is None or flags.get("trajectory") or flags.get("tests") or flags.get("ripple"):
        hooks["Stop"] = [group("hook proviso-verify", timeout=600)]
    if flags and flags.get("impact"):
        hooks["PreToolUse"] = [group("hook proviso-pretool", "Bash", timeout=60)]
    return {"hooks": hooks}


def write_proviso_files(
    harness_dir: str, repo_dir: str, probe_python: str | None, flags: dict[str, Any],
    python: str | None = None, brief: str | None = None, assets: str | None = None,
) -> str:
    os.makedirs(harness_dir, exist_ok=True)
    settings_path = os.path.join(harness_dir, "settings.json")
    with open(settings_path, "w", encoding="utf-8") as fh:
        json.dump(proviso_settings(python, probe_python, flags), fh, indent=2)
        fh.write("\n")
    folder = os.path.join(repo_dir, ".dc-engine")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, ".gitignore"), "w", encoding="utf-8") as fh:
        fh.write("*\n")
    with open(os.path.join(folder, "proviso.json"), "w", encoding="utf-8") as fh:
        json.dump({**flags, "python": os.path.abspath(probe_python) if probe_python else ""}, fh, indent=2)
        fh.write("\n")
    if flags.get("brief"):
        if not brief or not os.path.isfile(brief):
            raise FileNotFoundError(f"arm needs a brief file and none was found: {brief}")
        shutil.copyfile(brief, os.path.join(folder, "brief.md"))
    if flags.get("impact") or flags.get("ripple"):
        if not assets or not os.path.isdir(assets):
            raise FileNotFoundError(f"arm needs change-impact assets and none were found: {assets}")
        for name in os.listdir(assets):
            shutil.copyfile(os.path.join(assets, name), os.path.join(folder, name))
    return settings_path


def layer_mcp_config(
    python: str | None = None,
    probe_python: str | None = None,
    tools: str | None = "slim",
    contract_policy: str | None = "required",
) -> dict[str, Any]:
    py = os.path.abspath(python or sys.executable)
    server: dict[str, Any] = {
        "type": "stdio",
        "command": py,
        "args": server_mcp_args(
            "${CLAUDE_PROJECT_DIR:-.}",
            tools=tools, contract_policy=contract_policy,
        ),
    }
    pp = (probe_python or "").strip()
    if pp:
        server["env"] = {"DC_PROBE_PYTHON": os.path.abspath(pp)}
    return {"mcpServers": {"dc-engine": server}}


def write_layer_files(
    harness_dir: str,
    python: str | None = None,
    probe_python: str | None = None,
    *,
    tools: str | None = "slim",
    contract_policy: str | None = "required",
    hooks: bool = True,
) -> tuple[str, str | None]:
    os.makedirs(harness_dir, exist_ok=True)
    mcp_path = os.path.join(harness_dir, "mcp.json")
    with open(mcp_path, "w", encoding="utf-8") as fh:
        json.dump(
            layer_mcp_config(
                python, probe_python,
                tools=tools, contract_policy=contract_policy,
            ),
            fh, indent=2,
        )
        fh.write("\n")
    settings_path = None
    if hooks:
        settings_path = os.path.join(harness_dir, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as fh:
            json.dump(layer_settings(python, probe_python), fh, indent=2)
            fh.write("\n")
    return mcp_path, settings_path


def write_layer_repo_config(repo_dir: str) -> None:
    """enforce=block so Stop/PreToolUse hooks actually block."""
    folder = os.path.join(repo_dir, ".dc-engine")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "config.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"enforce": "block"}, fh, indent=2)
        fh.write("\n")


def cursor_argv(
    prompt: str,
    *,
    model: str,
    workspace: str,
    agent_bin: str = "agent",
) -> list[str]:
    """Cursor CLI flags, identical for both arms (no --sandbox; leave the default).

    `agent -p --output-format stream-json --force --trust --approve-mcps
    --workspace <run-copy> --model <model>`. Baseline has no MCP servers, so
    --approve-mcps is a no-op there.
    """
    m = (model or "").strip()
    if not m or m.lower() == "auto":
        raise ValueError(
            'refusing model "auto" (or empty). Both arms must use one fixed --model.'
        )
    if not workspace:
        raise ValueError("cursor runner requires an explicit --workspace path")
    return [
        agent_bin,
        "-p",
        "--output-format",
        "stream-json",
        "--force",
        "--trust",
        "--approve-mcps",
        "--workspace",
        workspace,
        "--model",
        m,
        prompt,
    ]


def claude_argv(
    prompt: str,
    arm: str,
    *,
    model: str,
    budget_usd: float,
    mcp_config: str | None = None,
    settings: str | None = None,
    claude_bin: str = "claude",
    bare: bool = True,
) -> list[str]:
    """Exact documented flags. Prompt is the `-p` argument.

    bare=False is for host-authenticated runs (no ANTHROPIC_API_KEY); the caller
    must then give the agent a clean environment (offline.claude_agent_env).
    """
    cfg = arm_config(arm)
    tools = LAYER_TOOLS if cfg["mcp"] else BASELINE_TOOLS
    argv = [
        claude_bin,
        *(["--bare"] if bare else []),
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        tools,
        "--max-budget-usd",
        str(budget_usd),
        "--model",
        model,
    ]
    if cfg.get("proviso"):
        if not settings:
            raise ValueError(f"{arm} arm requires --settings")
        argv.extend(["--settings", settings, "--include-hook-events"])
    if cfg["mcp"]:
        if not mcp_config:
            raise ValueError(f"{arm} arm requires --mcp-config")
        argv.extend(["--mcp-config", mcp_config, "--strict-mcp-config"])
        if cfg["hooks"]:
            if not settings:
                raise ValueError(f"{arm} arm requires --settings")
            argv.extend(["--settings", settings, "--include-hook-events"])
    return argv
