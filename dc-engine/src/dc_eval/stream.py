"""Parse Claude Code `--output-format stream-json --verbose` transcripts.

The last `type=result` line carries cost, usage, and turn count
(https://code.claude.com/docs/en/cli-reference).
"""

from __future__ import annotations

import json
from typing import Any, Iterable

READ_NAME_MARKERS = (
    "get_slice",
    "get_symbol",
    "repo_map",
    "file_outline",
    "find_symbol",
    "find_references",
    "dc_status",
)


def parse_stream(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def load_stream(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return parse_stream(fh.read())


def _result_event(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for evt in events:
        if evt.get("type") == "result":
            last = evt
    return last


def _usage(result: dict[str, Any]) -> dict[str, int]:
    usage = result.get("usage") or result.get("modelUsage") or {}
    if not isinstance(usage, dict):
        usage = {}
    def _n(*keys: str) -> int:
        for k in keys:
            v = usage.get(k)
            if v is None:
                continue
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
        return 0
    return {
        "input_tokens": _n("input_tokens", "inputTokens"),
        "output_tokens": _n("output_tokens", "outputTokens"),
        "cache_read_tokens": _n(
            "cache_read_input_tokens", "cache_read_tokens", "cacheReadInputTokens"
        ),
        "cache_creation_tokens": _n(
            "cache_creation_input_tokens", "cache_creation_tokens",
            "cacheCreationInputTokens",
        ),
    }


def _cost_usd(result: dict[str, Any]) -> float | None:
    for key in ("total_cost_usd", "totalCostUsd", "cost_usd"):
        v = result.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _content_blocks(evt: dict[str, Any]) -> list[Any]:
    msg = evt.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, list):
            return content
        if content:
            return [content]
    content = evt.get("content")
    if isinstance(content, list):
        return content
    return []


def _tool_uses(events: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(id, name) in stream order."""
    out: list[tuple[str, str]] = []
    for evt in events:
        if evt.get("type") not in ("assistant", "tool_use"):
            continue
        for block in _content_blocks(evt):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" or (evt.get("type") == "tool_use" and "name" in block):
                name = str(block.get("name") or evt.get("name") or "")
                tid = str(block.get("id") or evt.get("id") or "")
                if name:
                    out.append((tid, name))
        if evt.get("type") == "tool_use" and evt.get("name"):
            out.append((str(evt.get("id") or ""), str(evt.get("name"))))
    return out


def is_read_tool(name: str) -> bool:
    base = name.rsplit("__", 1)[-1]
    if name == "Read" or base == "Read":
        return True
    low = name.lower()
    return any(m in low for m in READ_NAME_MARKERS)


def _text_len(content: Any) -> int:
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(_text_len(p) for p in content)
    if isinstance(content, dict):
        if "text" in content:
            return _text_len(content.get("text"))
        if "content" in content:
            return _text_len(content.get("content"))
        return 0
    return len(str(content))


def _tool_result_chars(events: list[dict[str, Any]], id_to_name: dict[str, str]) -> int:
    total = 0
    for evt in events:
        if evt.get("type") not in ("user", "tool_result"):
            continue
        blocks = _content_blocks(evt)
        if evt.get("type") == "tool_result":
            blocks = [evt]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") not in ("tool_result", None) and "tool_use_id" not in block:
                if evt.get("type") != "tool_result":
                    continue
            tid = str(block.get("tool_use_id") or evt.get("tool_use_id") or "")
            name = id_to_name.get(tid, "")
            if not name or not is_read_tool(name):
                continue
            total += _text_len(block.get("content"))
    return total


def _nested_decision(obj: Any) -> str | None:
    if isinstance(obj, dict):
        dec = obj.get("decision")
        if isinstance(dec, str):
            return dec
        for v in obj.values():
            found = _nested_decision(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _nested_decision(v)
            if found:
                return found
    return None


def count_stop_hook_blocks(events: list[dict[str, Any]]) -> int:
    n = 0
    for evt in events:
        if evt.get("type") != "hook":
            continue
        name = str(
            evt.get("hook_event")
            or evt.get("hook_event_name")
            or evt.get("event")
            or evt.get("hook_name")
            or ""
        )
        if name.lower() not in ("stop",) and "stop" not in name.lower():
            continue
        dec = _nested_decision(evt)
        if dec == "block":
            n += 1
            continue
        stdout = evt.get("stdout")
        if isinstance(stdout, str) and '"decision": "block"' in stdout.replace("'", '"'):
            n += 1
    return n


def count_checkpoint_restores(tool_names: list[str]) -> int:
    n = 0
    for name in tool_names:
        low = name.lower()
        if "restore_checkpoint" in low or "dc_restore" in low:
            n += 1
    return n


def metrics_from_stream(text: str, wall_time_s: float | None = None) -> dict[str, Any]:
    events = parse_stream(text)
    result = _result_event(events)
    uses = _tool_uses(events)
    id_to_name = {tid: name for tid, name in uses if tid}
    names = [name for _, name in uses]
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    usage = _usage(result)
    turns = result.get("num_turns", result.get("numTurns"))
    try:
        turns_i = int(turns) if turns is not None else len(
            [e for e in events if e.get("type") == "assistant"]
        )
    except (TypeError, ValueError):
        turns_i = 0
    out: dict[str, Any] = {
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_read_tokens": usage["cache_read_tokens"],
        "cache_creation_tokens": usage["cache_creation_tokens"],
        "cost_usd": _cost_usd(result),
        "turns": turns_i,
        "tool_calls": counts,
        "tool_call_count": sum(counts.values()),
        "read_chars": _tool_result_chars(events, id_to_name),
        "stop_hook_blocks_stream": count_stop_hook_blocks(events),
        "checkpoints_restored": count_checkpoint_restores(names),
        "is_error": bool(result.get("is_error") or result.get("subtype") == "error"),
        "result_subtype": result.get("subtype"),
    }
    if wall_time_s is not None:
        out["wall_time_s"] = wall_time_s
    elif result.get("duration_ms") is not None:
        try:
            out["wall_time_s"] = float(result["duration_ms"]) / 1000.0
        except (TypeError, ValueError):
            pass
    return out
