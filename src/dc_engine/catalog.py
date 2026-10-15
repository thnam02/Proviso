"""Static dump of the MCP tool surface (names, descriptions, schemas).

Inspects the registered callables. No MCP session, no Engine index.
"""

from __future__ import annotations

import inspect
import json
import types
from typing import Any, Callable, Union, get_args, get_origin, get_type_hints

TOOL_MODES = ("slim", "full", "contracts")
SLIM_NAMES = (
    "dc_start",
    "dc_get_symbol",
    "dc_replace_symbol",
    "dc_contract",
    "dc_find",
)
CONTRACTS_NAMES = (
    "dc_contract",
    "dc_replace_symbol",
)
CONTRACT_POLICIES = ("required", "optional")


def parse_tools_mode(value: str) -> str:
    v = (value or "slim").strip().lower()
    if v not in TOOL_MODES:
        raise ValueError(f"unknown --tools {value!r}; use slim, full, or contracts")
    return v


def parse_contract_policy(value: str) -> str:
    v = (value or "required").strip().lower()
    if v not in CONTRACT_POLICIES:
        raise ValueError(f"unknown --contracts {value!r}; use required or optional")
    return v


def est_tokens(text: str) -> int:
    return (max(0, len(text)) + 3) // 4


def word_count(text: str) -> int:
    return len((text or "").split())


def _ann_schema(ann: Any) -> dict[str, Any]:
    if ann is inspect.Parameter.empty or ann is Any:
        return {}
    origin = get_origin(ann)
    args = get_args(ann)
    if origin is Union or origin is types.UnionType:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _ann_schema(non_none[0])
        return {"type": "object"}
    if origin is list:
        item = _ann_schema(args[0]) if args else {}
        return {"type": "array", "items": item or {}}
    if origin is dict:
        return {"type": "object"}
    if ann is str:
        return {"type": "string"}
    if ann is int:
        return {"type": "integer"}
    if ann is bool:
        return {"type": "boolean"}
    if ann is float:
        return {"type": "number"}
    if ann is dict:
        return {"type": "object"}
    if ann is list:
        return {"type": "array"}
    return {}


def json_schema_for(fn: Callable[..., Any]) -> dict[str, Any]:
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = dict(getattr(fn, "__annotations__", {}) or {})
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        schema = _ann_schema(hints.get(name, param.annotation))
        properties[name] = schema or {"type": "string"}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    out: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        out["required"] = required
    return out


def exposed_tool_text(name: str, description: str, schema: dict[str, Any]) -> str:
    schema_s = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    return f"{name}\n{description}\n{schema_s}"


def build_catalog(
    instructions: str,
    fns: list[Callable[..., Any]],
    mode: str = "slim",
) -> dict[str, Any]:
    tools: list[dict[str, Any]] = []
    for fn in fns:
        name = fn.__name__
        desc = inspect.getdoc(fn) or ""
        schema = json_schema_for(fn)
        text = exposed_tool_text(name, desc, schema)
        tools.append({
            "name": name,
            "description": desc,
            "input_schema": schema,
            "chars": len(text),
            "tokens": est_tokens(text),
            "text": text,
        })
    inst = (instructions or "").strip()
    parts = [inst] + [t["text"] for t in tools]
    total = "\n\n".join(p for p in parts if p)
    return {
        "mode": parse_tools_mode(mode),
        "instructions": inst,
        "instructions_chars": len(inst),
        "instructions_tokens": est_tokens(inst),
        "instructions_words": word_count(inst),
        "tools": tools,
        "tool_count": len(tools),
        "chars": len(total),
        "tokens": est_tokens(total),
        "text": total,
    }


def format_catalog(cat: dict[str, Any]) -> str:
    lines = [
        f"mode: {cat.get('mode')}",
        f"instructions: {cat.get('instructions_chars')} chars "
        f"(~{cat.get('instructions_tokens')} tokens, "
        f"{cat.get('instructions_words')} words)",
        "",
        "INSTRUCTIONS",
        cat.get("instructions") or "",
        "",
        f"| tool | chars | ~tokens |",
        "|---|---:|---:|",
        f"| (instructions) | {cat.get('instructions_chars')} | "
        f"{cat.get('instructions_tokens')} |",
    ]
    for t in cat.get("tools") or []:
        lines.append(f"| {t['name']} | {t['chars']} | {t['tokens']} |")
    lines.append(
        f"| TOTAL | {cat.get('chars')} | {cat.get('tokens')} |"
    )
    lines.append("")
    for t in cat.get("tools") or []:
        lines.append(f"TOOL {t['name']}")
        lines.append(f"description: {t.get('description') or ''}")
        lines.append("input schema:")
        lines.append(json.dumps(t.get("input_schema") or {}, indent=2))
        lines.append("")
    return "\n".join(lines)
