"""Idempotent merge of Claude Code hook + MCP entries.

Never overwrites keys we didn't write. `--uninstall` removes only our
matcher groups and the `dc-engine` MCP server.
"""

from __future__ import annotations

import json
import os
from typing import Any

HOOK_PRE = "dc-engine hook pre-edit"
HOOK_POST = "dc-engine hook post-edit"
HOOK_STOP = "dc-engine hook stop"
MCP_KEY = "dc-engine"
PRE_MATCHER = (
    "Edit|Write|MultiEdit|"
    "mcp__dc-engine__dc_replace_symbol|mcp__dc-engine__dc_insert_symbol"
)
POST_MATCHER = "Edit|Write|MultiEdit"


def install(root: str, claude_code: bool = True) -> str:
    notes: list[str] = []
    if claude_code:
        notes += _merge_settings(root)
        notes += _merge_mcp(root)
    return "\n".join(notes) or "nothing to install"


def uninstall(root: str) -> str:
    notes = _strip_settings(root) + _strip_mcp(root)
    return "\n".join(notes) or "nothing to uninstall"


def _settings_path(root: str) -> str:
    return os.path.join(root, ".claude", "settings.json")


def _mcp_path(root: str) -> str:
    return os.path.join(root, ".mcp.json")


def _load(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _dump(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _cmd_hook(command: str) -> dict[str, Any]:
    return {"type": "command", "command": command}


def _group(matcher: str | None, command: str) -> dict[str, Any]:
    g: dict[str, Any] = {"hooks": [_cmd_hook(command)]}
    if matcher:
        g["matcher"] = matcher
    return g


def _has_command(groups: list, command: str) -> bool:
    for g in groups:
        if not isinstance(g, dict):
            continue
        for h in g.get("hooks") or []:
            if isinstance(h, dict) and h.get("command") == command:
                return True
    return False


def _merge_settings(root: str) -> list[str]:
    path = _settings_path(root)
    data = _load(path)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks
    notes = []
    wanted = [
        ("PreToolUse", PRE_MATCHER, HOOK_PRE),
        ("PostToolUse", POST_MATCHER, HOOK_POST),
        ("Stop", None, HOOK_STOP),
    ]
    for event, matcher, command in wanted:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            groups = []
            hooks[event] = groups
        if _has_command(groups, command):
            notes.append(f"keep {event} → {command}")
            continue
        groups.append(_group(matcher, command))
        notes.append(f"add {event} → {command}")
    _dump(path, data)
    return notes


def _strip_settings(root: str) -> list[str]:
    path = _settings_path(root)
    if not os.path.isfile(path):
        return []
    data = _load(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return []
    ours = {HOOK_PRE, HOOK_POST, HOOK_STOP}
    notes = []
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        kept = []
        for g in groups:
            cmds = [h.get("command") for h in (g.get("hooks") or []) if isinstance(h, dict)]
            if any(c in ours for c in cmds):
                notes.append(f"remove {event} → {', '.join(c for c in cmds if c in ours)}")
                continue
            kept.append(g)
        hooks[event] = kept
        if not kept:
            del hooks[event]
    if not hooks:
        data.pop("hooks", None)
    _dump(path, data)
    return notes


def _merge_mcp(root: str) -> list[str]:
    path = _mcp_path(root)
    data = _load(path)
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    if MCP_KEY in servers:
        note = f"keep mcpServers.{MCP_KEY}"
        _dump(path, data)
        return [note]
    servers[MCP_KEY] = {
        "type": "stdio",
        "command": "dc-engine-mcp",
        "args": ["--root", "${CLAUDE_PROJECT_DIR:-.}"],
    }
    _dump(path, data)
    return [f"add mcpServers.{MCP_KEY}"]


def _strip_mcp(root: str) -> list[str]:
    path = _mcp_path(root)
    if not os.path.isfile(path):
        return []
    data = _load(path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or MCP_KEY not in servers:
        return []
    del servers[MCP_KEY]
    if not servers:
        data.pop("mcpServers", None)
    _dump(path, data)
    return [f"remove mcpServers.{MCP_KEY}"]
