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
import re
import sys
import traceback
from typing import Any

from . import active
from .contracts import list_saved, load_contract

EDIT_TOOLS = {"Edit", "Write", "MultiEdit"}
MCP_EDIT_NAMES = {"dc_replace_symbol", "dc_insert_symbol"}
BASH_TOOLS = {"Bash", "bash"}

# python[-3[.n]] -c  ... open(..., 'w'|'a'|...)
_PY_C = re.compile(r"\bpython(?:3(?:\.\d+)?)?\s+-c\b", re.I)
_OPEN_WRITE = re.compile(r"""open\s*\([^)]*['\"](?:w|a|r\+|w\+|wb|wt|ab)""")
_REDIRECT_PY = re.compile(r"(?:>>?)\s*['\"]?([^\s'\";&|]+\.py)\b")
_TEE_PY = re.compile(r"\btee\b[^\n]*\b[\w./\\-]+\.py\b")
_SED_I_PY = re.compile(r"\bsed\s+[^\n]*-i[^\n]*\.py\b")
_MV_CP_PY = re.compile(
    r"\b(?:mv|cp)\b[^\n]*\s+['\"]?(?:(?:\./)?[\w./\\-]+\.py)['\"]?\s*(?:[;&|)\]]|$)"
)


def handle(event: str, payload: dict[str, Any], root: str | None = None) -> dict[str, Any]:
    """Return the JSON object to print. Never raises."""
    try:
        cwd = root or payload.get("cwd") or os.getcwd()
        cwd = os.path.abspath(str(cwd))
        mode = active.enforce_mode(cwd)
        if mode == "off":
            return {}
        active.ensure_session_snapshot(cwd)
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


def command_writes_py(command: str) -> bool:
    """True when a shell command clearly writes a .py file (or python -c open-write)."""
    if not command or not str(command).strip():
        return False
    s = str(command)
    if _PY_C.search(s) and _OPEN_WRITE.search(s):
        return True
    if _REDIRECT_PY.search(s):
        return True
    if _TEE_PY.search(s):
        return True
    if _SED_I_PY.search(s):
        return True
    if _MV_CP_PY.search(s):
        return True
    return False


def _pre_edit(payload: dict[str, Any], root: str, mode: str) -> dict[str, Any]:
    tool = str(payload.get("tool_name") or "")
    if tool in BASH_TOOLS:
        cmd = ""
        inp = payload.get("tool_input") or {}
        if isinstance(inp, dict):
            cmd = str(inp.get("command") or "")
        if command_writes_py(cmd) and not active.get_active_id(root):
            reason = ("No active delta contract. Shell writes to .py files are "
                      "blocked; call dc_create_contract first.")
            if mode == "warn":
                return _pre_context(reason)
            return _deny(reason)
        return {}
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
        return _stop_no_active(root, mode, payload)
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


def _stop_no_active(root: str, mode: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Backstop: .py changed with no contract (block once); warn if closed unsatisfied."""
    sess = active.ensure_session_snapshot(root)
    changed = active.py_files_changed(root)
    already = bool(sess.get("py_bypass_blocked"))
    stop_active = bool(payload.get("stop_hook_active"))
    if changed and not already and not stop_active:
        sess["py_bypass_blocked"] = True
        active.save_session(root, sess)
        reason = ("Python files changed with no active contract "
                  f"({', '.join(changed[:4])}{'…' if len(changed) > 4 else ''}). "
                  "Call dc_create_contract before editing.")
        if mode == "warn":
            return _stop_context(reason)
        return {"decision": "block", "reason": reason}
    closed_msg = _closed_unsatisfied_warning(root, sess)
    if closed_msg:
        return {
            "systemMessage": closed_msg,
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": closed_msg,
            },
        }
    return {}


def _closed_unsatisfied_warning(root: str, sess: dict[str, Any]) -> str:
    warned = {str(x) for x in (sess.get("closed_warned") or [])}
    newest = None
    for c in list_saved(root):
        if c.status != "closed":
            continue
        score = c.close_score
        if score is None or score >= 1.0 - 1e-12:
            continue
        if c.id in warned:
            continue
        if newest is None or (c.closed_at or "") > (newest.closed_at or ""):
            newest = c
    if newest is None:
        return ""
    warned.add(newest.id)
    sess["closed_warned"] = sorted(warned)
    active.save_session(root, sess)
    reason = newest.close_reason or "(no reason)"
    score = newest.close_score
    score_s = f"{score:.1f}" if isinstance(score, float) else str(score)
    return f"contract {newest.id} closed unsatisfied (score {score_s}): {reason}"


def _stop_context(note: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": note,
        }
    }


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
