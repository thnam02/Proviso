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


def stream_has_result(text: str) -> bool:
    return any(evt.get("type") == "result" for evt in parse_stream(text))


def count_model_requests(events: list[dict[str, Any]]) -> int:
    """Distinct model_call_id values, else the number of assistant events."""
    ids: list[str] = []
    for evt in events:
        mid = evt.get("model_call_id")
        if not mid and isinstance(evt.get("message"), dict):
            mid = evt["message"].get("model_call_id")
        if mid:
            ids.append(str(mid))
    if ids:
        return len(set(ids))
    return sum(1 for e in events if e.get("type") == "assistant")


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


def est_result_tokens(n_chars: int) -> int:
    """~tokens = chars/4 (same rounding as dc-engine views.est_tokens)."""
    return (max(0, int(n_chars)) + 3) // 4


def normalize_tool_name(name: str) -> str:
    """Strip MCP prefixes: mcp__dc-engine__dc_start / dc-engine-dc_start → dc_start."""
    s = (name or "").strip()
    if not s:
        return "unknown"
    if "__" in s:
        s = s.rsplit("__", 1)[-1]
    if s.startswith("dc-engine-"):
        s = s[len("dc-engine-"):]
    return s


def is_dc_engine_tool(name: str) -> bool:
    return normalize_tool_name(name).startswith("dc_")


def count_read_calls(tool_calls: dict[str, int] | None) -> int:
    """Read + Grep invocations (context tools)."""
    n = 0
    for raw, c in (tool_calls or {}).items():
        key = normalize_tool_name(str(raw)).lower()
        if key in ("read", "grep"):
            try:
                n += int(c)
            except (TypeError, ValueError):
                continue
    return n


def count_dc_engine_calls(tool_calls: dict[str, int] | None) -> int:
    n = 0
    for raw, c in (tool_calls or {}).items():
        if not is_dc_engine_tool(str(raw)):
            continue
        try:
            n += int(c)
        except (TypeError, ValueError):
            continue
    return n


def count_dc_contract_calls(tool_calls: dict[str, int] | None) -> int:
    n = 0
    for raw, c in (tool_calls or {}).items():
        if normalize_tool_name(str(raw)) != "dc_contract":
            continue
        try:
            n += int(c)
        except (TypeError, ValueError):
            continue
    return n


def payload_text(obj: Any) -> str:
    """Flatten Claude/Cursor tool-result payloads to the text the agent saw."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, list):
        return "".join(payload_text(p) for p in obj)
    if not isinstance(obj, dict):
        return str(obj)
    if "text" in obj:
        return payload_text(obj.get("text"))
    if "content" in obj:
        return payload_text(obj.get("content"))
    sc = obj.get("structuredContent")
    if isinstance(sc, dict) and sc.get("result") is not None:
        return payload_text(sc.get("result"))
    return ""


def _text_len(content: Any) -> int:
    return len(payload_text(content))


def result_payload_chars(success: Any) -> int:
    """Chars of a completed tool result. Prefer totalChars when the CLI reports it."""
    if not isinstance(success, dict):
        return _text_len(success)
    raw = success.get("totalChars")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    n = _text_len(success)
    if n:
        return n
    try:
        return len(json.dumps(success, ensure_ascii=False))
    except (TypeError, ValueError):
        return 0


def pack_tool_sizes(items: list[tuple[str, int]]) -> dict[str, Any]:
    """Aggregate (tool_name, chars) into per-tool and dc-engine metrics."""
    by: dict[str, int] = {}
    dc_chars: dict[str, int] = {}
    dc_list: list[dict[str, Any]] = []
    total = 0
    for raw_name, n in items:
        name = normalize_tool_name(raw_name)
        n = max(0, int(n))
        by[name] = by.get(name, 0) + n
        total += n
        if is_dc_engine_tool(name):
            dc_chars[name] = dc_chars.get(name, 0) + n
            dc_list.append({
                "tool": name,
                "chars": n,
                "tokens": est_result_tokens(n),
            })
    dc_list.sort(key=lambda r: (-int(r["chars"]), str(r["tool"])))
    return {
        "tool_result_chars": by,
        "tool_result_tokens": {k: est_result_tokens(v) for k, v in by.items()},
        "tool_result_chars_total": total,
        "tool_result_tokens_total": est_result_tokens(total),
        "dc_engine_result_chars": dc_chars,
        "dc_engine_results": dc_list,
        "dc_engine_largest": dc_list[:5],
    }


def tool_sizes_from_claude_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    uses = _tool_uses(events)
    id_to_name = {tid: name for tid, name in uses if tid}
    items: list[tuple[str, int]] = []
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
            name = id_to_name.get(tid) or str(block.get("name") or evt.get("name") or "")
            if not name:
                continue
            items.append((name, result_payload_chars(block.get("content"))))
    return pack_tool_sizes(items)


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
    token_total = (
        usage["input_tokens"] + usage["output_tokens"]
        + usage["cache_read_tokens"] + usage["cache_creation_tokens"]
    )
    n_req = count_model_requests(events)
    out: dict[str, Any] = {
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_read_tokens": usage["cache_read_tokens"],
        "cache_creation_tokens": usage["cache_creation_tokens"],
        "tokens": token_total,
        "model_requests": n_req,
        "tokens_per_request": (token_total / n_req) if n_req else None,
        "cost_usd": _cost_usd(result),
        "turns": turns_i,
        "tool_calls": counts,
        "tool_call_count": sum(counts.values()),
        "read_calls": count_read_calls(counts),
        "dc_engine_calls": count_dc_engine_calls(counts),
        "dc_contract_calls": count_dc_contract_calls(counts),
        "read_chars": _tool_result_chars(events, id_to_name),
        **tool_sizes_from_claude_events(events),
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
