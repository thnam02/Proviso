"""Load the dc-engine MCP catalog via subprocess. Never imports dc_engine."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any


def dump_engine_catalog(tools: str = "slim", timeout: int = 30) -> dict[str, Any] | None:
    env = os.environ.copy()
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = env.get("PYTHONPATH", "")
    if src not in path.split(os.pathsep):
        env["PYTHONPATH"] = src + (os.pathsep + path if path else "")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "dc_engine", "tools", "--json", "--tools", tools],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def load_catalogs() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for mode in ("full", "slim", "contracts"):
        cat = dump_engine_catalog(mode)
        if cat:
            out[mode] = cat
    return out


def catalog_report_lines(catalogs: dict[str, dict[str, Any]]) -> list[str]:
    if not catalogs:
        return []
    lines = ["## Tool surface (static)", ""]
    lines.append(
        "Exact text dc-engine exposes: server instructions plus each tool's "
        "name, description, and input schema. ~tokens = chars/4."
    )
    lines.append("")
    order = [m for m in ("full", "slim", "contracts") if m in catalogs]
    if "full" in catalogs and "slim" in catalogs:
        f, s = catalogs["full"], catalogs["slim"]
        lines.append(
            f"Before (full): **{f.get('chars')}** chars "
            f"(~{f.get('tokens')} tokens, {f.get('tool_count')} tools). "
            f"After (slim): **{s.get('chars')}** chars "
            f"(~{s.get('tokens')} tokens, {s.get('tool_count')} tools)."
        )
        lines.append("")
    for mode in order:
        cat = catalogs[mode]
        lines.append(f"### {mode}")
        lines.append("")
        lines.append(
            f"instructions: {cat.get('instructions_chars')} chars "
            f"(~{cat.get('instructions_tokens')} tokens, "
            f"{cat.get('instructions_words')} words)"
        )
        lines.append("")
        lines.append("| tool | chars | ~tokens |")
        lines.append("|---|---:|---:|")
        lines.append(
            f"| (instructions) | {cat.get('instructions_chars')} | "
            f"{cat.get('instructions_tokens')} |"
        )
        for t in cat.get("tools") or []:
            lines.append(
                f"| {t.get('name')} | {t.get('chars')} | {t.get('tokens')} |"
            )
        lines.append(f"| TOTAL | {cat.get('chars')} | {cat.get('tokens')} |")
        lines.append("")
        if cat.get("instructions"):
            lines.append("```")
            lines.append(str(cat["instructions"]).rstrip())
            lines.append("```")
            lines.append("")
        for t in cat.get("tools") or []:
            lines.append(f"#### {t.get('name')}")
            lines.append("")
            lines.append("```")
            lines.append(str(t.get("text") or "").rstrip())
            lines.append("```")
            lines.append("")
    return lines
