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
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from . import active
from .contracts import list_saved, load_contract
from .jsonio import exclusive_lock

EDIT_TOOLS = {"Edit", "Write", "MultiEdit"}
MCP_EDIT_NAMES = {"dc_replace_symbol", "dc_insert_symbol"}
BASH_TOOLS = {"Bash", "bash"}

MSG_NO_CONTRACT_EDIT = (
    "No active delta contract. Call dc_contract(action=create) or "
    "dc_create_contract with the symbols you will change before editing "
    "Python files."
)
MSG_NO_CONTRACT_SHELL = (
    "No active delta contract. Shell writes to .py files are "
    "blocked; call dc_contract(action=create) or dc_create_contract first."
)

CURSOR_PERMISSION_EVENTS = {
    "preToolUse", "beforeShellExecution", "beforeMCPExecution", "pre-edit",
}

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
    return _run_logged("claude", event, payload, root, _handle_body)


def _handle_body(event: str, payload: dict[str, Any], cwd: str) -> dict[str, Any]:
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


def run_cli(event: str, argv_root: str | None = None, fmt: str = "claude") -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception as exc:
        _append_invocation_log(
            argv_root or os.getcwd(), fmt, event, {},
            decision="none", duration_ms=0,
            error=f"{type(exc).__name__}: {exc}",
            traceback_s=traceback.format_exc(),
        )
        payload = {}
    if fmt == "cursor":
        out = handle_cursor(event, payload, argv_root)
    else:
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
            reason = MSG_NO_CONTRACT_SHELL
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
        reason = MSG_NO_CONTRACT_EDIT
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
                f"dc_contract(action=amend) / dc_amend_contract if this file is in scope.")
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
    changed = _uncovered_by_satisfied_close(root, active.py_files_changed(root))
    already = bool(sess.get("py_bypass_blocked"))
    stop_active = bool(payload.get("stop_hook_active"))
    if changed and not already and not stop_active:
        sess["py_bypass_blocked"] = True
        active.save_session(root, sess)
        reason = ("Python files changed with no active contract "
                  f"({', '.join(changed[:4])}{'…' if len(changed) > 4 else ''}). "
                  "Call dc_contract(action=create) or dc_create_contract before editing.")
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


def _iso_epoch(text: str) -> float | None:
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _uncovered_by_satisfied_close(root: str, changed: list[str]) -> list[str]:
    """Drop files last modified before the newest contract that closed fully satisfied.

    Without this, an agent that created, satisfied and closed a contract was told
    "Python files changed with no active contract" at Stop and wasted several
    turns trying to create a new one (seen in every Claude Code layer run).
    Files edited after that close still count as uncovered.
    """
    if not changed:
        return changed
    newest: float | None = None
    for c in list_saved(root):
        if c.status != "closed" or c.close_score is None or c.close_score < 1.0 - 1e-12:
            continue
        t = _iso_epoch(c.closed_at) if c.closed_at else None
        if t is not None and (newest is None or t > newest):
            newest = t
    if newest is None:
        return changed
    out = []
    for rel in changed:
        path = os.path.join(root, rel.replace("/", os.sep))
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = time.time()  # deleted after the close: treat as uncovered
        if mtime > newest + 1.0:
            out.append(rel)
    return out


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


_HOOK_NOTES: list[str] = []


def _log_line(_root: str, line: str) -> None:
    """Record a human note for the invocation log (not a separate log line)."""
    _HOOK_NOTES.append(line)


def _hook_timestamp() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(now.microsecond / 1000):03d}Z"


def _tool_and_file(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    tool = payload.get("tool_name") or payload.get("tool")
    inp = payload.get("tool_input") or {}
    file = None
    if isinstance(inp, dict):
        file = inp.get("file_path") or inp.get("path") or inp.get("filePath")
    file = file or payload.get("file_path") or payload.get("path")
    cmd = payload.get("command")
    if not tool and cmd:
        tool = "Shell"
    return (str(tool) if tool else None, str(file) if file else None)


def _decision_of(out: dict[str, Any], fmt: str) -> str:
    if not isinstance(out, dict):
        return "none"
    if fmt == "cursor":
        perm = out.get("permission")
        if perm == "deny":
            return "deny"
        if perm == "allow":
            return "allow"
        if out.get("followup_message"):
            return "followup"
        return "none"
    hso = out.get("hookSpecificOutput") if isinstance(out.get("hookSpecificOutput"), dict) else {}
    perm = hso.get("permissionDecision") if hso else None
    if perm == "deny":
        return "deny"
    if perm == "allow":
        return "allow"
    if out.get("decision") == "block":
        return "followup"
    return "none"


def _append_invocation_log(
    root: str,
    fmt: str,
    event: str,
    payload: dict[str, Any],
    *,
    decision: str,
    duration_ms: int,
    error: str | None = None,
    traceback_s: str | None = None,
    message: str | None = None,
) -> None:
    tool, file = _tool_and_file(payload if isinstance(payload, dict) else {})
    rec: dict[str, Any] = {
        "timestamp": _hook_timestamp(),
        "format": fmt,
        "event": event,
        "decision": decision,
        "duration_ms": duration_ms,
    }
    if tool:
        rec["tool"] = tool
    if file:
        rec["file"] = file
    if message:
        rec["message"] = message
    if error:
        rec["error"] = error
    if traceback_s:
        rec["traceback"] = traceback_s
    try:
        folder = os.path.join(os.path.abspath(str(root or ".")), ".dc-engine")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "hooks.log")
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with exclusive_lock(path):
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
    except OSError:
        pass


def _run_logged(
    fmt: str,
    event: str,
    payload: dict[str, Any],
    root: str | None,
    body,
) -> dict[str, Any]:
    _HOOK_NOTES.clear()
    t0 = time.perf_counter()
    payload = payload if isinstance(payload, dict) else {}
    if fmt == "cursor":
        cwd = _cursor_root(payload, root)
    else:
        cwd = root or payload.get("cwd") or os.getcwd()
        cwd = os.path.abspath(str(cwd))
    error = None
    tb = None
    try:
        out = body(event, payload, cwd)
        if not isinstance(out, dict):
            out = {}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc()
        out = {} if fmt == "claude" else _cursor_allow(event)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    _append_invocation_log(
        cwd, fmt, event, payload,
        decision=_decision_of(out, fmt),
        duration_ms=duration_ms,
        error=error,
        traceback_s=tb,
        message="\n".join(_HOOK_NOTES) if _HOOK_NOTES else None,
    )
    return out


def _cursor_root(payload: dict[str, Any], root: str | None) -> str:
    if root:
        return os.path.abspath(str(root))
    cwd = payload.get("cwd")
    if cwd:
        return os.path.abspath(str(cwd))
    roots = payload.get("workspace_roots") or []
    if isinstance(roots, list) and roots:
        return os.path.abspath(str(roots[0]))
    return os.getcwd()


def _cursor_allow(event: str) -> dict[str, Any]:
    if event in CURSOR_PERMISSION_EVENTS:
        return {"permission": "allow"}
    return {}


def _cursor_deny(reason: str) -> dict[str, Any]:
    return {"permission": "deny", "agent_message": reason}


def _loop_count(payload: dict[str, Any]) -> int:
    try:
        return int(payload.get("loop_count") or 0)
    except (TypeError, ValueError):
        return 0


def handle_cursor(event: str, payload: dict[str, Any], root: str | None = None) -> dict[str, Any]:
    """Cursor hooks.json stdio adapter. Never raises. Permission hooks always
    return a schema-valid object (`permission` allow|deny) so invalid JSON
    cannot fail-closed and block the agent.
    """
    return _run_logged("cursor", event, payload, root, _handle_cursor_body)


def _handle_cursor_body(event: str, payload: dict[str, Any], cwd: str) -> dict[str, Any]:
    mode = active.enforce_mode(cwd)
    if mode == "off":
        return _cursor_allow(event)
    active.ensure_session_snapshot(cwd)
    if event in ("preToolUse", "pre-edit"):
        return _cursor_pre_tool(payload, cwd, mode)
    if event == "beforeShellExecution":
        return _cursor_shell(payload, cwd, mode)
    if event == "beforeMCPExecution":
        return {"permission": "allow"}
    if event in ("afterFileEdit",):
        return _cursor_after_edit(payload, cwd)
    if event == "stop":
        return _cursor_stop(payload, cwd, mode)
    return _cursor_allow(event)


def _cursor_pre_tool(payload: dict[str, Any], root: str, mode: str) -> dict[str, Any]:
    tool = str(payload.get("tool_name") or "Write")
    if tool in BASH_TOOLS or tool in {"Shell", "shell"}:
        return _cursor_shell(payload, root, mode)
    inp = payload.get("tool_input") or {}
    if isinstance(inp, str):
        try:
            parsed = json.loads(inp)
            inp = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            inp = {}
    if not _is_edit_tool(tool) and tool not in EDIT_TOOLS:
        return {"permission": "allow"}
    paths = _edited_paths(tool if tool in EDIT_TOOLS else "Write", inp, root)
    if not paths:
        for key in ("file_path", "path", "filePath"):
            if isinstance(inp, dict) and inp.get(key):
                paths = [_abs(root, str(inp.get(key)))]
                break
    py_paths = [p for p in paths if _is_repo_python(root, p)]
    if not py_paths:
        return {"permission": "allow"}
    cid = active.get_active_id(root)
    if not cid:
        if mode == "warn":
            _log_line(root, f"WARN preToolUse: {MSG_NO_CONTRACT_EDIT}")
            return {"permission": "allow"}
        _log_line(root, f"DENY preToolUse: {MSG_NO_CONTRACT_EDIT}")
        return _cursor_deny(MSG_NO_CONTRACT_EDIT)
    contract = load_contract(root, cid)
    if contract is None:
        return {"permission": "allow"}
    target_files = _target_files(root, contract.targets)
    stray = [p for p in py_paths if os.path.realpath(p) not in target_files]
    if stray and len(stray) == len(py_paths):
        rel = os.path.relpath(stray[0], root)
        note = (f"{rel} isn't a target of contract {cid}. "
                f"dc_contract(action=amend) / dc_amend_contract if this file is in scope.")
        _log_line(root, f"WARN preToolUse: {note}")
        return {"permission": "allow"}
    return {"permission": "allow"}


def _cursor_shell(payload: dict[str, Any], root: str, mode: str) -> dict[str, Any]:
    cmd = str(payload.get("command") or "")
    inp = payload.get("tool_input") or {}
    if not cmd and isinstance(inp, dict):
        cmd = str(inp.get("command") or "")
    if command_writes_py(cmd) and not active.get_active_id(root):
        if mode == "warn":
            _log_line(root, f"WARN beforeShellExecution: {MSG_NO_CONTRACT_SHELL}")
            return {"permission": "allow"}
        _log_line(root, f"DENY beforeShellExecution: {MSG_NO_CONTRACT_SHELL}")
        return _cursor_deny(MSG_NO_CONTRACT_SHELL)
    return {"permission": "allow"}


def _cursor_after_edit(payload: dict[str, Any], root: str) -> dict[str, Any]:
    path = str(payload.get("file_path") or payload.get("path") or "")
    if path:
        active.record_edited_path(root, path)
    return {}


def _cursor_followup_text(report: Any) -> str:
    line = report.one_line() if hasattr(report, "one_line") else str(report)
    return (
        f"{line}\nFix every ✗ before stopping. dc_replace_symbol / "
        "dc_contract(action=amend) / dc_amend_contract, then "
        "dc_contract(action=check) / dc_check_contract."
    )


def _cursor_stop(payload: dict[str, Any], root: str, mode: str) -> dict[str, Any]:
    cid = active.get_active_id(root)
    loops = _loop_count(payload)
    if not cid:
        return _cursor_stop_no_active(root, mode, payload, loops)
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
    follow = _cursor_followup_text(report)
    hist = active.stop_history(root)
    same_three = (len(hist) >= 2 and hist[-1] == hist[-2]
                  and abs(hist[-1] - report.score) < 1e-12)
    release = same_three or loops >= 3 or mode == "warn"
    if release:
        warn = "⚠ allowing stop; contract still unsatisfied:\n" + text
        _log_line(root, f"STOP-RELEASE: {warn}")
        return {}
    active.record_stop_block(root, report.score)
    _log_line(root, f"STOP-FOLLOWUP: {follow}")
    return {"followup_message": follow}


def _cursor_stop_no_active(
    root: str, mode: str, payload: dict[str, Any], loops: int,
) -> dict[str, Any]:
    sess = active.ensure_session_snapshot(root)
    changed = _uncovered_by_satisfied_close(root, active.py_files_changed(root))
    already = bool(sess.get("py_bypass_blocked"))
    if changed and not already and loops < 3:
        sess["py_bypass_blocked"] = True
        active.save_session(root, sess)
        reason = ("Python files changed with no active contract "
                  f"({', '.join(changed[:4])}{'…' if len(changed) > 4 else ''}). "
                  "Call dc_contract(action=create) or dc_create_contract before editing.")
        if mode == "warn":
            _log_line(root, f"WARN stop: {reason}")
            return {}
        _log_line(root, f"STOP-FOLLOWUP: {reason}")
        return {"followup_message": reason}
    closed_msg = _closed_unsatisfied_warning(root, sess)
    if closed_msg:
        _log_line(root, f"STOP-RELEASE: {closed_msg}")
        return {}
    return {}

