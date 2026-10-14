"""Claude Code CLI invocations for the two eval arms.

Flags match https://code.claude.com/docs/en/cli-reference and
https://code.claude.com/docs/en/headless — `claude --bare -p`,
`--output-format stream-json --verbose`, `--permission-mode acceptEdits`,
`--allowedTools`, `--max-budget-usd`, plus `--mcp-config` / `--settings`
on the layer arm.
"""

from __future__ import annotations

import json
import os
from typing import Any

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


def layer_settings() -> dict[str, Any]:
    """Hooks with enforce=block, same matcher groups as `dc-engine install`."""
    def group(command: str, matcher: str | None = None) -> dict[str, Any]:
        g: dict[str, Any] = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            g["matcher"] = matcher
        return g
    return {
        "hooks": {
            "PreToolUse": [group(HOOK_PRE, PRE_MATCHER)],
            "PostToolUse": [group(HOOK_POST, POST_MATCHER)],
            "Stop": [group(HOOK_STOP)],
        }
    }


def layer_mcp_config() -> dict[str, Any]:
    return {
        "mcpServers": {
            "dc-engine": {
                "type": "stdio",
                "command": "dc-engine-mcp",
                "args": ["--root", "${CLAUDE_PROJECT_DIR:-.}"],
            }
        }
    }


def write_layer_files(harness_dir: str) -> tuple[str, str]:
    os.makedirs(harness_dir, exist_ok=True)
    settings_path = os.path.join(harness_dir, "settings.json")
    mcp_path = os.path.join(harness_dir, "mcp.json")
    with open(settings_path, "w", encoding="utf-8") as fh:
        json.dump(layer_settings(), fh, indent=2)
        fh.write("\n")
    with open(mcp_path, "w", encoding="utf-8") as fh:
        json.dump(layer_mcp_config(), fh, indent=2)
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


def claude_argv(
    prompt: str,
    arm: str,
    *,
    model: str,
    budget_usd: float,
    mcp_config: str | None = None,
    settings: str | None = None,
    claude_bin: str = "claude",
) -> list[str]:
    """Exact documented flags. Prompt is the `-p` argument."""
    if arm not in ("baseline", "layer"):
        raise ValueError(f"unknown arm: {arm}")
    tools = LAYER_TOOLS if arm == "layer" else BASELINE_TOOLS
    argv = [
        claude_bin,
        "--bare",
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
    if arm == "layer":
        if not mcp_config or not settings:
            raise ValueError("layer arm requires --mcp-config and --settings paths")
        argv.extend([
            "--mcp-config", mcp_config,
            "--settings", settings,
            "--strict-mcp-config",
            "--include-hook-events",
        ])
    return argv
