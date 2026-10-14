"""Claude Code hook handlers: make agents create a contract before they edit.

`dc-engine hook <event>` reads hook JSON on stdin and prints JSON on stdout
using the field names from https://code.claude.com/docs/en/hooks
(PreToolUse: hookSpecificOutput.permissionDecision; Stop: decision/reason).
Any internal error is swallowed: we allow the action and append a line to
`.dc-engine/hooks.log` so a broken hook never wedged a session.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any

from . import active
from .contracts import load_contract

EDIT_TOOLS = {"Edit", "Write", "MultiEdit"}
MCP_EDIT_NAMES = {"dc_replace_symbol", "dc_insert_symbol"}


def handle(event: str, payload: dict[str, Any], root: str | None = None) -> dict[str, Any]:
    """Return the JSON object to print. Never raises."""
    try:
        cwd = root or payload.get("cwd") or os.getcwd()
        cwd = os.path.abspath(str(cwd))
        mode = active.enforce_mode(cwd)
        if mode == "off":
            return {}
        if event == "pre-edit":
            return _pre_edit(payload, cwd, mode)
        if event == "post-edit":
            return _post_edit(payload, cwd, mode)
        if event == "stop":
            return _stop(payload, cwd, mode)
        return {}
    except Exception as exc:
        _log(root or payload.get("cwd") or os.getcwd(), exc)
        return {}


def run_cli(event: str, argv_root: str | None = None) -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception as exc:
        _log(argv_root or os.getcwd(), exc)
        payload = {}
    out = handle(event, payload, argv_root)
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    return 0


def _pre_edit(payload: dict[str, Any], root: str, mode: str) -> dict[str, Any]:
    tool = str(payload.get("tool_name") or "")
    if not _is_edit_tool(tool):
        return {}
    paths = _edited_paths(tool, payload.get("tool_input") or {}, root)
    py_paths = [p for p in paths if _is_repo_python(root, p)]
    mcp_edit = _is_mcp_edit(tool)
    if not py_paths and not mcp_edit:
        return {}  # non-Python / outside repo / .dc-engine: always allow
    cid = active.get_active_id(root)
    if not cid:
        reason = ("No active delta contract. Call dc_create_contract with the "
                  "symbols you will change before editing Python files.")
        if mode == "warn":
            return _pre_context(reason)
        return _deny(reason)
    contract = load_contract(root, cid)
    if contract is None:
        return {}
    target_files = _target_files(root, contract.targets)
    stray = [p for p in py_paths if os.path.realpath(p) not in target_files]
    if stray and len(stray) == len(py_paths):
        rel = os.path.relpath(stray[0], root)
        note = (f"{rel} isn't a target of contract {cid}. "
                f"dc_amend_contract if this file is in scope.")
        return _pre_context(note)
    return {}


def _post_edit(payload: dict[str, Any], root: str, mode: str) -> dict[str, Any]:
    tool = str(payload.get("tool_name") or "")
    if tool not in EDIT_TOOLS:
        return {}  # MCP edits already auto-check via replace/insert
    paths = _edited_paths(tool, payload.get("tool_input") or {}, root)
    if not any(_is_repo_python(root, p) for p in paths):
        return {}
    cid = active.get_active_id(root)
    if not cid:
        return {}
    from .delta import auto_check_line
    from .engine import Engine
    engine = Engine(root, typecheck="off")
    try:
        line = auto_check_line(engine)
    finally:
        engine.close()
    if not line:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": line,
        }
    }


def _stop(payload: dict[str, Any], root: str, mode: str) -> dict[str, Any]:
    cid = active.get_active_id(root)
    if not cid:
        return {}
    from .delta import check_contract
    from .engine import Engine
    engine = Engine(root, typecheck="off")
    try:
        report = check_contract(engine, cid)
    finally:
        engine.close()
    if isinstance(report, str):
        return {}
    if report.score >= 1.0 - 1e-12:
        return {}
    text = str(report)
    stop_active = bool(payload.get("stop_hook_active"))
    hist = active.stop_history(root)
    same_three = (len(hist) >= 2 and hist[-1] == hist[-2]
                  and abs(hist[-1] - report.score) < 1e-12)
    if stop_active or same_three or mode == "warn":
        return {
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": "⚠ allowing stop; contract still unsatisfied:\n" + text,
            }
        }
    active.record_stop_block(root, report.score)
    if mode == "off":
        return {}
    return {"decision": "block", "reason": text}


def _is_edit_tool(name: str) -> bool:
    if name in EDIT_TOOLS:
        return True
    return _is_mcp_edit(name)


def _is_mcp_edit(name: str) -> bool:
    return name.startswith("mcp__") and name.rsplit("__", 1)[-1] in MCP_EDIT_NAMES


def _edited_paths(tool: str, tool_input: Any, root: str) -> list[str]:
    if not isinstance(tool_input, dict):
        return []
    if tool in EDIT_TOOLS:
        p = tool_input.get("file_path") or tool_input.get("path")
        return [_abs(root, p)] if p else []
    suffix = tool.rsplit("__", 1)[-1] if "__" in tool else tool
    if suffix == "dc_replace_symbol":
        name = tool_input.get("name") or tool_input.get("ref")
        return _paths_for_ref(root, str(name or ""))
    if suffix == "dc_insert_symbol":
        path = tool_input.get("path")
        if path:
            return [_abs(root, path)]
        after = tool_input.get("after")
        if after:
            return _paths_for_ref(root, str(after))
    return []


def _paths_for_ref(root: str, ref: str) -> list[str]:
    if not ref:
        return []
    try:
        from .engine import Engine
        engine = Engine(root, typecheck="off")
        try:
            engine.ensure_fresh()
            sym, err = engine.resolve_ref(ref)
            if sym:
                return [engine.abspath(sym.path)]
        finally:
            engine.close()
    except Exception:
        pass
    return []


def _target_files(root: str, targets: list[str]) -> set[str]:
    out: set[str] = set()
    try:
        from .engine import Engine
        engine = Engine(root, typecheck="off")
        try:
            engine.ensure_fresh()
            for ref in targets:
                sym, err = engine.resolve_ref(ref)
                if sym:
                    out.add(os.path.realpath(engine.abspath(sym.path)))
        finally:
            engine.close()
    except Exception:
        pass
    return out


def _is_repo_python(root: str, path: str) -> bool:
    if not path:
        return False
    real = os.path.realpath(_abs(root, path))
    base = os.path.realpath(root)
    if real != base and not real.startswith(base + os.sep):
        return False
    rel = os.path.relpath(real, base)
    parts = rel.split(os.sep)
    if ".dc-engine" in parts:
        return False
    return real.endswith(".py")


def _abs(root: str, path: str) -> str:
    path = os.path.expanduser(str(path))
    return path if os.path.isabs(path) else os.path.abspath(os.path.join(root, path))


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _pre_context(note: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": note,
        }
    }


def _log(root: str, exc: BaseException) -> None:
    try:
        folder = os.path.join(os.path.abspath(str(root or ".")), ".dc-engine")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "hooks.log"), "a", encoding="utf-8") as fh:
            fh.write(traceback.format_exc() if isinstance(exc, BaseException) else str(exc))
            fh.write("\n")
    except OSError:
        pass
