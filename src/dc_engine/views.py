"""Compact, token-budgeted views of the index for agents.

Every view returns plain text sized to a token budget. Rules of thumb:
signatures and one-line docstrings instead of bodies, bodies only for the
symbols being worked on, and an explicit pointer to the tool that loads
anything that was left out (so the agent never has to guess or re-read).
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from typing import TYPE_CHECKING

from .contracts import CREATE_CONTRACT_EXAMPLE, apply_auto_imports, split_import_target
from .parser import Symbol

if TYPE_CHECKING:
    from .engine import Engine


# Method names so common on built-in types (dict.update, str.split, ...) that a
# name match against repo symbols would mostly be wrong; no "possibly" hints.
_COMMON_METHODS = {n for t in (dict, list, str, bytes, set, tuple, int, float)
                   for n in dir(t) if not n.startswith("_")} | {"read", "write", "close", "flush", "seek", "tell"}

SMALL_REPO_TOKENS = 8000
DEFAULT_REPO_MAP_TOKENS = 800
DEFAULT_SLICE_TOKENS = 1500
DEFAULT_START_TOKENS = 2500
GET_SYMBOL_MAX_TOKENS = 300
_TASK_STOP = {
    "a", "an", "the", "to", "of", "in", "for", "and", "or", "on", "is", "be",
    "it", "by", "with", "from", "that", "this", "should", "must", "not",
    "call", "calls", "code", "file", "function", "make", "please",
}


def is_test_symbol(sym: Symbol) -> bool:
    path = sym.path.replace("\\", "/")
    base = os.path.basename(path)
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith("_test.py"):
        return True
    if "/tests/" in f"/{path}/" or path.startswith("tests/"):
        return True
    return sym.name.startswith("test_")


def est_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token for code)."""
    return (len(text) + 3) // 4


def first_line(doc: str | None, limit: int = 80) -> str:
    if not doc:
        return ""
    line = doc.strip().splitlines()[0].strip()
    return line if len(line) <= limit else line[: limit - 1] + "…"


def loc(sym: Symbol) -> str:
    return f"{sym.path}:L{sym.def_line}"


def one_liner(sym: Symbol, with_doc: bool = True) -> str:
    doc = first_line(sym.docstring) if with_doc else ""
    return f"{sym.qualname}  {loc(sym)}  {sym.signature}" + (f"  — {doc}" if doc else "")


class Views:
    def __init__(self, engine: Engine):
        self.e = engine

    # ------------------------------------------------------------------
    def repo_map(self, path_prefix: str = "", max_tokens: int = DEFAULT_REPO_MAP_TOKENS) -> str:
        files = sorted(
            (m for m in self.e.store.file_meta().values() if m.path.startswith(path_prefix)),
            key=lambda m: m.path,
        )
        if not files:
            return f"No Python files under '{path_prefix or '.'}'."
        by_file: dict[str, list[Symbol]] = defaultdict(list)
        for s in self.e.store.all_symbols():
            if s.path.startswith(path_prefix):
                by_file[s.path].append(s)

        def depth(s: Symbol) -> int:
            return s.qualname.count(".") - self.e.module_of(s.path).count(".") - 1

        def render(level: int) -> list[str]:
            out: list[str] = []
            for m in files:
                syms = by_file.get(m.path, [])
                doc = first_line(m.doc, 60)
                err = f"  [parse error: {m.error}]" if m.error else ""
                if level >= 3:
                    out.append(f"{m.path} ({m.lines} lines, {len(syms)} symbols){err}")
                    continue
                out.append(f"{m.path} ({m.lines} lines)" + (f" — {doc}" if doc and level == 0 else "") + err)
                if level == 2:
                    top = [s for s in syms if s.parent is None]
                    names = []
                    for s in top:
                        if s.kind == "class":
                            kids = [k.name for k in syms if k.parent == s.qualname and k.kind == "method"]
                            names.append(f"class {s.name}[{', '.join(kids)}]" if kids else f"class {s.name}")
                        else:
                            names.append(f"{s.name}()")
                    if names:
                        out.append("  " + "; ".join(names))
                    continue
                for s in syms:
                    indent = "  " * (depth(s) + 1)
                    doc1 = first_line(s.docstring, 60) if level == 0 else ""
                    out.append(f"{indent}{s.signature}  :{s.def_line}" + (f"  — {doc1}" if doc1 else ""))
            return out

        for level in range(4):
            lines = render(level)
            text = "\n".join(lines)
            if est_tokens(text) <= max_tokens:
                note = ["", "(compressed view; pass path_prefix to see full signatures)"] if level else []
                return "\n".join(lines + note)
        # Still too big: truncate the coarsest view.
        out, used = [], 0
        for line in lines:
            cost = est_tokens(line + "\n")
            if used + cost > max_tokens - 30:
                break
            out.append(line)
            used += cost
        out.append(f"… {len(lines) - len(out)} more files; narrow with path_prefix.")
        return "\n".join(out)

    # ------------------------------------------------------------------
    def find_symbol(self, query: str, limit: int = 15) -> str:
        hits = self.e.store.search(query, limit + 1)
        if not hits:
            return f"No symbols matching '{query}'."
        lines = [one_liner(s) for s in hits[:limit]]
        if len(hits) > limit:
            lines.append("… more matches; refine the query.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def _callee_rows(self, sym: Symbol):
        resolved, unresolved, external = [], [], []
        for row in self.e.store.callees_of(sym.qualname):
            if row["callee"]:
                resolved.append(row)
            elif row["external"]:
                external.append(row)
            else:
                unresolved.append(row)
        return resolved, unresolved, external

    def get_symbol(self, ref: str, include_body: bool = False) -> str:
        sym, err = self.e.resolve_ref(ref)
        if err:
            return err
        out = [f"{sym.qualname}  ({sym.kind})  {sym.path}:L{sym.start_line}-{sym.end_line}",
               sym.signature]
        if sym.docstring:
            doc = sym.docstring.strip()
            out.append("doc: " + (doc if len(doc) <= 600 else doc[:599] + "…"))
        if sym.parent:
            out.append(f"in: {sym.parent}")
        if sym.kind == "class":
            members = self.e.store.children(sym.qualname)
            if members:
                out.append("members:")
                out += [f"  {m.signature}  :{m.def_line}" + (f"  — {first_line(m.docstring, 60)}" if m.docstring else "")
                        for m in members]
        else:
            resolved, unresolved, external = self._callee_rows(sym)
            calls = sorted({r["callee"] for r in resolved})
            if calls:
                out.append("calls: " + ", ".join(calls))
            if external:
                out.append("external: " + ", ".join(sorted({r["external"] for r in external})))
            if unresolved:
                out.append("unresolved calls: " + ", ".join(sorted({r["expr"] for r in unresolved})))
        callers = self.e.store.callers_of(sym.qualname)
        if callers:
            names = sorted({r["caller"] for r in callers})
            shown = ", ".join(names[:8]) + (f" (+{len(names) - 8} more)" if len(names) > 8 else "")
            out.append(f"called by: {shown}")
        if include_body:
            out.append("```python")
            out.append(self.e.symbol_source(sym).rstrip("\n"))
            out.append("```")
            return "\n".join(out)
        if sym.kind != "class":
            body = self.e.symbol_source(sym)
            out.append(f"(body: {sym.end_line - sym.start_line + 1} lines, ~{est_tokens(body)} tokens; "
                       f"include_body=true to load)")
        text = "\n".join(out)
        if est_tokens(text) <= GET_SYMBOL_MAX_TOKENS:
            return text
        # Keep signature + location; drop long doc / member lists until it fits.
        head = out[:2]
        tail = [ln for ln in out[2:] if ln.startswith("(body:")]
        kept = head[:]
        used = est_tokens("\n".join(kept + tail))
        for ln in out[2:]:
            if ln in tail:
                continue
            cost = est_tokens(ln + "\n")
            if used + cost > GET_SYMBOL_MAX_TOKENS - 8:
                kept.append("… (truncated; include_body=true for source)")
                break
            kept.append(ln)
            used += cost
        kept.extend(tail)
        text = "\n".join(kept)
        if est_tokens(text) > GET_SYMBOL_MAX_TOKENS:
            room = max(0, GET_SYMBOL_MAX_TOKENS * 4 - 40)
            text = text[:room] + "\n… (truncated; include_body=true for source)"
        return text

    # ------------------------------------------------------------------
    def find_references(self, ref: str, limit: int = 40) -> str:
        sym, err = self.e.resolve_ref(ref)
        if err:
            return err
        rows = self.e.store.callers_of(sym.qualname)
        out = [f"References to {sym.qualname}:"]
        if rows:
            for r in rows[:limit]:
                out.append(f"  {r['path']}:L{r['line']}  in {r['caller']}  ({r['expr']})")
            if len(rows) > limit:
                out.append(f"  … +{len(rows) - limit} more")
        else:
            out.append("  (no resolved call sites)")
        possible = [r for r in self.e.store.unresolved_mentions(sym.name)
                    if r["expr"].split(".")[-1] == sym.name]
        if possible:
            out.append(f"Possible (receiver type unknown, matched by name '{sym.name}'):")
            for r in possible[:15]:
                out.append(f"  {r['path']}:L{r['line']}  in {r['caller']}  ({r['expr']})")
            if len(possible) > 15:
                out.append(f"  … +{len(possible) - 15} more")
        return "\n".join(out)

    # ------------------------------------------------------------------
    def file_outline(self, path: str) -> str:
        path = path.lstrip("./")
        meta = self.e.store.get_file(path)
        if not meta:
            return f"File not indexed: {path}"
        syms = self.e.store.symbols_in_file(path)
        mod = self.e.module_of(path)
        out = [f"{path} ({meta.lines} lines)  module {mod}" + (f" — {first_line(meta.doc)}" if meta.doc else "")]
        if meta.error:
            out.append(f"[parse error: {meta.error}]")
        for s in syms:
            indent = "  " * (s.qualname.count(".") - mod.count("."))
            out.append(f"{indent}{s.signature}  :{s.def_line}-{s.end_line}"
                       + (f"  — {first_line(s.docstring, 60)}" if s.docstring else ""))
        return "\n".join(out)

    # ------------------------------------------------------------------
    def tests_for_targets(self, targets: list[Symbol]) -> list[Symbol]:
        """Test functions that call the targets, or whose names match them."""
        found: list[Symbol] = []
        seen: set[str] = set()
        tnames = {t.qualname for t in targets}
        short = {t.name.lower() for t in targets if len(t.name) > 2}

        def add(sym: Symbol) -> None:
            if sym.qualname in seen or sym.qualname in tnames:
                return
            if not is_test_symbol(sym):
                return
            seen.add(sym.qualname)
            found.append(sym)

        for t in targets:
            for row in self.e.store.callers_of(t.qualname):
                for s in self.e.store.symbols_by_qualname(row["caller"]):
                    add(s)
        for s in self.e.store.all_symbols():
            if not is_test_symbol(s):
                continue
            blob = (s.name + " " + (s.docstring or "")).lower()
            if any(n in blob for n in short):
                add(s)
        return found

    def match_task_symbols(self, task: str, limit: int = 5) -> list[Symbol]:
        words = [
            w for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", (task or "").lower())
            if len(w) > 2 and w not in _TASK_STOP
        ]
        if not words:
            return []
        scored: list[tuple[int, int, Symbol]] = []
        for s in self.e.store.all_symbols():
            blob = f"{s.name} {s.qualname} {s.docstring or ''}".lower()
            score = 0
            for w in words:
                if s.name.lower() == w:
                    score += 3
                elif w in s.name.lower() or w in s.qualname.lower():
                    score += 2
                elif w in blob:
                    score += 1
            if score:
                scored.append((score, len(s.qualname), s))
        scored.sort(key=lambda x: (-x[0], x[1], x[2].qualname))
        out: list[Symbol] = []
        seen: set[str] = set()
        for _, _, s in scored:
            if s.qualname in seen:
                continue
            seen.add(s.qualname)
            out.append(s)
            if len(out) >= limit:
                break
        return out

    def contract_template(self, task: str, symbols: list[Symbol]) -> str:
        targets = [s.qualname for s in symbols] or list(CREATE_CONTRACT_EXAMPLE["targets"])
        imports: list[tuple[str, str]] = []
        for s in symbols:
            pair = split_import_target(s.qualname, s.kind, s.parent)
            if pair:
                imports.append(pair)
        setup, _ = apply_auto_imports("", imports)
        if symbols:
            call_name = symbols[0].name
            if symbols[0].kind == "method":
                cls = (symbols[0].parent or "").rsplit(".", 1)[-1]
                call = f"{cls}(...).{call_name}(...)"
            else:
                call = f"{call_name}(...)"
            change = [{
                "id": "change-1",
                "setup": setup,
                "call": call,
                "expect_new": {"raises": "ValueError"},
            }]
            preserve = [{
                "id": "preserve-1",
                "setup": setup,
                "call": call,
                "expect_old": {"raises": "ValueError"},
                "expect_new": {"raises": "ValueError"},
            }]
            obj = {
                "task": task or CREATE_CONTRACT_EXAMPLE["task"],
                "targets": targets,
                "must_change": change,
                "must_preserve": preserve,
            }
        else:
            obj = dict(CREATE_CONTRACT_EXAMPLE)
            obj["task"] = task or obj["task"]
        return json.dumps(obj, indent=2)

    def start(self, task: str, hint_symbols: list[str] | None = None,
              max_tokens: int = DEFAULT_START_TOKENS) -> str:
        stats = self.e.store.stats()
        repo_tokens = int(stats.get("chars") or 0) // 4
        small = repo_tokens < SMALL_REPO_TOKENS
        picked: list[Symbol] = []
        seen: set[str] = set()
        for ref in hint_symbols or []:
            sym, err = self.e.resolve_ref(ref)
            if sym and sym.qualname not in seen:
                seen.add(sym.qualname)
                picked.append(sym)
        if not picked:
            picked = self.match_task_symbols(task)

        sections: list[str] = [
            f"== REPO  ~{repo_tokens} tokens, {stats.get('files', 0)} files, "
            f"{stats.get('symbols', 0)} symbols",
        ]
        if small:
            sections.append(
                f"This repo is small (under {SMALL_REPO_TOKENS} tokens). "
                "Read files directly. Call dc_contract(action=create) before "
                "editing (hooks still require a contract). Skip extra "
                "exploration tools."
            )
        else:
            map_budget = max(200, min(800, max_tokens // 4))
            sections.append("== MAP")
            sections.append(self.repo_map("", map_budget))
            if picked:
                used = est_tokens("\n".join(sections))
                slice_budget = max(400, max_tokens - used - 600)
                sections.append("== SLICES")
                sections.append(self.get_slice(
                    [s.qualname for s in picked], 1, slice_budget, True,
                    include_tests=True,
                ))
        sections.append("== CONTRACT TEMPLATE")
        sections.append(self.contract_template(task, picked))
        sections.append("== CONTRACT EXAMPLE")
        sections.append(json.dumps(CREATE_CONTRACT_EXAMPLE, indent=2))
        sections.append(
            "Fill setup/call/expect_new, then dc_contract(action=create). "
            + ("Do not call dc_find separately." if small
               else "Use dc_find if this is not enough.")
        )
        text = "\n".join(sections)
        if est_tokens(text) <= max_tokens:
            return text
        # Trim from the end of MAP/SLICES, keep REPO + template.
        keep_head = sections[0]
        tmpl_i = next(i for i, s in enumerate(sections) if s == "== CONTRACT TEMPLATE")
        tail = "\n".join(sections[tmpl_i:])
        room = max_tokens - est_tokens(keep_head) - est_tokens(tail) - 20
        mid = "\n".join(sections[1:tmpl_i])
        if est_tokens(mid) > room > 40:
            # character-approximate trim
            mid = mid[: max(0, room * 4)] + "\n… (truncated to max_tokens)"
        return keep_head + "\n" + mid + "\n" + tail

    def get_slice(self, refs: list[str], depth: int = 1,
                  max_tokens: int = DEFAULT_SLICE_TOKENS,
                  include_bodies: bool = True, include_tests: bool = False,
                  include_test_bodies: bool = False) -> str:
        targets: list[Symbol] = []
        errors: list[str] = []
        for ref in refs:
            sym, err = self.e.resolve_ref(ref)
            if err:
                errors.append(err)
            elif sym.qualname not in {t.qualname for t in targets}:
                targets.append(sym)
        if not targets:
            return "\n".join(errors) or "No targets."

        target_names = {t.qualname for t in targets}
        callees: dict[str, int] = {}
        callers: dict[str, tuple[int, str, int]] = {}  # name -> (distance, path, line)
        frontier = set(target_names)
        for dist in range(1, max(1, depth) + 1):
            nxt: set[str] = set()
            for q in frontier:
                for row in self.e.store.callees_of(q):
                    c = row["callee"]
                    if c and c not in target_names and c not in callees:
                        callees[c] = dist
                        nxt.add(c)
                for row in self.e.store.callers_of(q):
                    c = row["caller"]
                    if c not in target_names and c not in callers:
                        callers[c] = (dist, row["path"], row["line"])
                        nxt.add(c)
            frontier = nxt

        def sym_of(q: str) -> Symbol | None:
            hits = self.e.store.symbols_by_qualname(q)
            return hits[0] if hits else None

        # Fixed (non-body) parts first, so bodies get whatever budget is left.
        context: list[str] = []
        for t in targets:
            if t.parent:
                parent = sym_of(t.parent)
                if parent:
                    sibs = [m.name for m in self.e.store.children(parent.qualname)
                            if m.qualname != t.qualname]
                    context.append(f"{t.qualname} is in {parent.signature} ({loc(parent)})"
                                   + (f"; other members: {', '.join(sibs[:20])}" if sibs else ""))
        callee_lines = []
        for q, dist in sorted(callees.items(), key=lambda kv: (kv[1], kv[0])):
            s = sym_of(q)
            if s:
                callee_lines.append(("  " * dist) + one_liner(s))
        caller_lines = []
        for q, (dist, path, line) in sorted(callers.items(), key=lambda kv: (kv[1][0], kv[0])):
            s = sym_of(q)
            sig = s.signature if s else ""
            caller_lines.append(("  " * dist) + f"{q}  {path}:L{line}  {sig}")
        unresolved_lines = []
        for t in targets:
            if t.kind == "class":
                continue
            _, unresolved, _ = self._callee_rows(t)
            for row in unresolved:
                name = row["expr"].split(".")[-1]
                cands = [] if name in _COMMON_METHODS else \
                    [s.qualname for s in self.e.store.search(name, 50) if s.name == name][:3]
                hint = f" → possibly {', '.join(cands)}" if cands else " (external or dynamic)"
                unresolved_lines.append(f"  {row['expr']}  L{row['line']}{hint}")

        MAX_NEIGHBOURS = 25

        def capped(lines: list[str], what: str) -> list[str]:
            if len(lines) <= MAX_NEIGHBOURS:
                return lines
            return lines[:MAX_NEIGHBOURS] + [f"  … +{len(lines) - MAX_NEIGHBOURS} more {what} "
                                             f"(dc_find_references for the full list)"]

        tail: list[str] = []
        if context:
            tail += ["== CONTEXT"] + context
        if callee_lines:
            tail += [f"== CALLEES (depth {depth})"] + capped(callee_lines, "callees")
        if caller_lines:
            tail += [f"== CALLERS (depth {depth})"] + capped(caller_lines, "callers")
        if unresolved_lines:
            tail += ["== UNRESOLVED CALLS IN TARGETS"] + unresolved_lines[:20]
        tail += errors
        tail.append("Load any other body with dc_get_symbol(name, include_body=true).")
        tail_text = "\n".join(tail)

        budget = max_tokens - est_tokens(tail_text) - 40
        target_blocks = []
        for t in targets:
            header = f"== TARGET {t.qualname}  ({t.kind})  {t.path}:L{t.start_line}-{t.end_line}"
            src = self.e.symbol_source(t).rstrip("\n")
            if t.kind == "class":
                members = self.e.store.children(t.qualname)
                src_short = "\n".join([t.signature] + [f"    {m.signature}  :{m.def_line}" for m in members])
                block = f"{header}\n{src_short}"
            else:
                body_block = f"{header}\n```python\n{src}\n```"
                if include_bodies and est_tokens(body_block) <= budget:
                    block = body_block
                else:
                    reason = "budget" if include_bodies else "include_bodies=false"
                    block = (f"{header}\n{t.signature}\n"
                             + (f"doc: {first_line(t.docstring)}\n" if t.docstring else "")
                             + f"(body ~{est_tokens(src)} tokens omitted: {reason}; dc_get_symbol to load)")
            budget -= est_tokens(block)
            target_blocks.append(block)

        test_blocks: list[str] = []
        if include_tests:
            for t in self.tests_for_targets(targets)[:8]:
                header = f"== TEST {t.qualname}  {t.path}:L{t.start_line}-{t.end_line}"
                src = self.e.symbol_source(t).rstrip("\n")
                body_block = f"{header}\n```python\n{src}\n```"
                want_body = include_bodies and include_test_bodies
                if want_body and est_tokens(body_block) <= budget:
                    block = body_block
                else:
                    reason = (
                        "budget" if want_body
                        else ("include_test_bodies=false" if include_bodies
                              else "include_bodies=false")
                    )
                    block = (f"{header}\n{t.signature}\n"
                             f"(body ~{est_tokens(src)} tokens omitted: {reason}; dc_get_symbol to load)")
                budget -= est_tokens(block)
                test_blocks.append(block)

        out = "\n".join(target_blocks + test_blocks) + "\n" + tail_text
        head = (f"SLICE {', '.join(t.qualname for t in targets)}  "
                f"(depth {depth}, {len(callees)} callees, {len(callers)} callers, ~{est_tokens(out)} tokens)")
        return head + "\n" + out
