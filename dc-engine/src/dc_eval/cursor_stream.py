"""Parse Cursor CLI `--output-format stream-json` transcripts.

Event shapes: https://cursor.com/docs/cli/reference/output-format.md
(`tool_call` started/completed with `call_id`; terminal `result`).
Usage blocks are summed when present; they are not in the public result schema.
"""

from __future__ import annotations

import json
from typing import Any

from .stream import (
    count_dc_contract_calls, count_dc_engine_calls, count_model_requests,
    count_read_calls, is_dc_engine_tool, normalize_tool_name, parse_stream,
    pack_tool_sizes, result_payload_chars,
)

LIMIT_MARKERS = (
    "usage limit",
    "plan limit",
    "rate limit",
    "hit your limit",
    "spend limit",
    "request limit",
    "quota exceeded",
    "upgrade your plan",
    "on-demand spending",
    "you've reached",
    "you have reached",
    "limit exceeded",
    "usage cap",
)


def is_limit_error(stderr: str = "", stream: str = "") -> bool:
    blob = f"{stderr}\n{stream}".lower()
    return any(m in blob for m in LIMIT_MARKERS)


def _n(obj: dict[str, Any], *keys: str) -> int | None:
    for k in keys:
        if k not in obj or obj.get(k) is None:
            continue
        try:
            return int(obj[k])
        except (TypeError, ValueError):
            continue
    return None


def _usage_from_obj(obj: dict[str, Any]) -> dict[str, int] | None:
    if not isinstance(obj, dict):
        return None
    block = obj
    if obj.get("type") == "usage" or "inputTokens" in obj or "cacheReadTokens" in obj:
        block = obj.get("usage") if isinstance(obj.get("usage"), dict) else obj
    elif isinstance(obj.get("usage"), dict):
        block = obj["usage"]
    else:
        return None
    inp = _n(block, "inputTokens", "input_tokens")
    out = _n(block, "outputTokens", "output_tokens")
    cread = _n(block, "cacheReadTokens", "cache_read_tokens", "cacheReadInputTokens")
    cwrite = _n(block, "cacheWriteTokens", "cache_write_tokens", "cacheCreationInputTokens")
    if inp is None and out is None and cread is None and cwrite is None:
        return None
    return {
        "input_tokens": inp or 0,
        "output_tokens": out or 0,
        "cache_read_tokens": cread or 0,
        "cache_write_tokens": cwrite or 0,
    }


def _unwrap_tool(tc: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(tc, dict):
        return "", {}
    if "function" in tc and isinstance(tc["function"], dict):
        fn = tc["function"]
        return str(fn.get("name") or "function"), fn
    for key, val in tc.items():
        if isinstance(val, dict) and key.endswith("ToolCall"):
            name = key[: -len("ToolCall")]
            return name, val
    return "", tc


def _tool_key(name: str) -> str:
    return name.lower().replace("_", "")


def _read_chars_from_success(success: dict[str, Any]) -> int:
    raw = success.get("totalChars")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    content = success.get("content")
    if isinstance(content, str):
        return len(content)
    if content is None:
        return 0
    return len(str(content))


def _web_query(args: dict[str, Any]) -> str | None:
    for k in ("searchTerm", "query", "search_term", "q"):
        v = args.get(k)
        if v:
            return str(v)
    return None


def _web_url(args: dict[str, Any]) -> str | None:
    for k in ("url", "uri"):
        v = args.get(k)
        if v:
            return str(v)
    return None


def metrics_from_cursor_stream(text: str, wall_time_s: float | None = None) -> dict[str, Any]:
    events = parse_stream(text)
    result: dict[str, Any] = {}
    for evt in events:
        if evt.get("type") == "result":
            result = evt
    usage_sum = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    usage_blocks = 0
    for evt in events:
        u = _usage_from_obj(evt)
        if u is None:
            continue
        usage_blocks += 1
        for k, v in u.items():
            usage_sum[k] += v
    usage_missing = usage_blocks == 0
    if usage_missing:
        tokens: dict[str, Any] = {
            "input_tokens": None,
            "output_tokens": None,
            "cache_read_tokens": None,
            "cache_write_tokens": None,
            "tokens": None,
        }
    else:
        total = (
            usage_sum["input_tokens"]
            + usage_sum["cache_read_tokens"]
            + usage_sum["cache_write_tokens"]
            + usage_sum["output_tokens"]
        )
        tokens = {**usage_sum, "tokens": total}

    tool_calls: dict[str, int] = {}
    seen_started: set[str] = set()
    read_chars = 0
    files_written: list[str] = []
    hook_denials = 0
    hook_followups = 0
    restores = 0
    web_queries: list[str] = []
    web_urls: list[str] = []
    size_items: list[tuple[str, int]] = []
    dc_named: dict[str, int] = {}

    for evt in events:
        et = evt.get("type")
        if et == "hook":
            perm = str(
                (evt.get("permission") or "")
                or ((evt.get("output") or {}) if isinstance(evt.get("output"), dict) else {}).get("permission")
                or ""
            ).lower()
            if perm == "deny":
                hook_denials += 1
            out = evt.get("output") if isinstance(evt.get("output"), dict) else {}
            if evt.get("followup_message") or (isinstance(out, dict) and out.get("followup_message")):
                hook_followups += 1
            continue
        if et != "tool_call":
            continue
        call_id = str(evt.get("call_id") or "")
        name, body = _unwrap_tool(evt.get("tool_call"))
        if not name:
            name = str(evt.get("name") or "unknown")
        if evt.get("subtype") == "started":
            if call_id:
                if call_id in seen_started:
                    continue
                seen_started.add(call_id)
            tool_calls[name] = tool_calls.get(name, 0) + 1
            if "restore" in name.lower() and "checkpoint" in name.lower():
                restores += 1
            args = body.get("args") if isinstance(body.get("args"), dict) else {}
            if _tool_key(name) in ("mcp", "mcptool"):
                tn = str(args.get("toolName") or args.get("name") or "")
                if tn:
                    nn = normalize_tool_name(tn)
                    dc_named[nn] = dc_named.get(nn, 0) + 1
            elif is_dc_engine_tool(name):
                nn = normalize_tool_name(name)
                dc_named[nn] = dc_named.get(nn, 0) + 1
            if name.lower() == "write":
                p = args.get("path") or args.get("file_path")
                if p:
                    files_written.append(str(p))
            key = _tool_key(name)
            if key == "websearch":
                q = _web_query(args)
                if q:
                    web_queries.append(q)
            elif key == "webfetch":
                u = _web_url(args)
                if u:
                    web_urls.append(u)
        elif evt.get("subtype") == "completed":
            result_blob = body.get("result") if isinstance(body.get("result"), dict) else {}
            success = result_blob.get("success") if isinstance(result_blob, dict) else None
            args = body.get("args") if isinstance(body.get("args"), dict) else {}
            size_name = name
            if _tool_key(name) in ("mcp", "mcptool"):
                size_name = str(
                    args.get("toolName") or args.get("name") or name
                )
            if isinstance(success, dict):
                if _tool_key(name) == "read":
                    read_chars += _read_chars_from_success(success)
                if name.lower() == "write":
                    p = success.get("path")
                    if p and str(p) not in files_written:
                        files_written.append(str(p))
                size_items.append((size_name, result_payload_chars(success)))
            elif result_blob:
                size_items.append((size_name, result_payload_chars(result_blob)))
            if "restore" in name.lower() and "checkpoint" in name.lower() and call_id not in seen_started:
                restores += 1

    duration_ms = result.get("duration_ms")
    try:
        duration_ms_i = int(duration_ms) if duration_ms is not None else None
    except (TypeError, ValueError):
        duration_ms_i = None
    web_search_count = 0
    web_fetch_count = 0
    for n, c in tool_calls.items():
        key = _tool_key(n)
        if key == "websearch":
            web_search_count += c
        elif key == "webfetch":
            web_fetch_count += c
    n_req = count_model_requests(events)
    merged_calls = dict(tool_calls)
    merged_calls.update(dc_named)
    out: dict[str, Any] = {
        **tokens,
        "turns": None,  # Cursor stream-json has no turn count
        "tool_calls": tool_calls,
        "tool_call_count": sum(tool_calls.values()),
        "read_calls": count_read_calls(merged_calls),
        "dc_engine_calls": count_dc_engine_calls(merged_calls),
        "dc_engine_tool_calls": dc_named,
        "dc_contract_calls": count_dc_contract_calls(merged_calls),
        "read_chars": read_chars,
        **pack_tool_sizes(size_items),
        "web_search_count": web_search_count,
        "web_fetch_count": web_fetch_count,
        "web_call_count": web_search_count + web_fetch_count,
        "web_queries": web_queries,
        "web_urls": web_urls,
        "files_written": files_written,
        "model_requests": n_req,
        "tokens_per_request": (
            (tokens.get("tokens") / n_req)
            if (not usage_missing and n_req and tokens.get("tokens") is not None)
            else None
        ),
        "usage_missing": usage_missing,
        "usage_blocks": usage_blocks,
        "is_error": bool(result.get("is_error") or result.get("subtype") == "error"),
        "result_subtype": result.get("subtype"),
        "duration_ms": duration_ms_i,
        "stop_hook_blocks_stream": hook_followups,
        "hook_denials_stream": hook_denials,
        "checkpoints_restored": restores,
        "cost_usd": None,  # filled by prices.estimate
        "cost_estimated": True,
    }
    if wall_time_s is not None:
        out["wall_time_s"] = wall_time_s
    elif duration_ms_i is not None:
        out["wall_time_s"] = duration_ms_i / 1000.0
    return out


def summarize_hooks_log(log_text: str) -> dict[str, Any]:
    """Parse JSONL hook invocations. Legacy DENY/WARN lines are ignored."""
    calls_by_event: dict[str, int] = {}
    denials = 0
    followups = 0
    errors = 0
    ok_calls = 0
    total = 0
    for ln in log_text.splitlines():
        s = ln.strip()
        if not s.startswith("{"):
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or "event" not in obj:
            continue
        total += 1
        ev = str(obj.get("event") or "")
        if ev:
            calls_by_event[ev] = calls_by_event.get(ev, 0) + 1
        if obj.get("error"):
            errors += 1
        else:
            ok_calls += 1
        dec = obj.get("decision")
        if dec == "deny":
            denials += 1
        elif dec == "followup":
            followups += 1
    return {
        "hook_calls": total,
        "hook_calls_by_event": calls_by_event,
        "hook_denials": denials,
        "hook_stop_followups": followups,
        "hook_errors": errors,
        "hooks_active": ok_calls > 0,
    }


def count_hooks_log_effects(log_text: str) -> int:
    """Successful (no error) hook invocations in the log."""
    s = summarize_hooks_log(log_text)
    return int(s.get("hook_calls") or 0) - int(s.get("hook_errors") or 0)
