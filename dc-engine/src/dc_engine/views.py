"""Compact, token-budgeted views of the index for agents.

Every view returns plain text sized to a token budget. Rules of thumb:
signatures and one-line docstrings instead of bodies, bodies only for the
symbols being worked on, and an explicit pointer to the tool that loads
anything that was left out (so the agent never has to guess or re-read).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from .parser import Symbol

if TYPE_CHECKING:
    from .engine import Engine


# Method names so common on built-in types (dict.update, str.split, ...) that a
# name match against repo symbols would mostly be wrong; no "possibly" hints.
_COMMON_METHODS = {n for t in (dict, list, str, bytes, set, tuple, int, float)
                   for n in dir(t) if not n.startswith("_")} | {"read", "write", "close", "flush", "seek", "tell"}


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
    def repo_map(self, path_prefix: str = "", max_tokens: int = 2000) -> str:
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
        elif sym.kind != "class":
            body = self.e.symbol_source(sym)
            out.append(f"(body: {sym.end_line - sym.start_line + 1} lines, ~{est_tokens(body)} tokens; "
                       f"include_body=true to load)")
        return "\n".join(out)

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
    def get_slice(self, refs: list[str], depth: int = 1, max_tokens: int = 4000,
                  include_bodies: bool = True) -> str:
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

        out = "\n".join(target_blocks) + "\n" + tail_text
        head = (f"SLICE {', '.join(t.qualname for t in targets)}  "
                f"(depth {depth}, {len(callees)} callees, {len(callers)} callers, ~{est_tokens(out)} tokens)")
        return head + "\n" + out
