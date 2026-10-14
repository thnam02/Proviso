"""Engine: the single entry point used by the MCP server, the CLI and tests."""

from __future__ import annotations

import os
import re
import time

from .checks import Checker
from .edit_gate import EditGate
from .indexer import Indexer
from .parser import Symbol, module_name
from .store import Store
from .views import Views, est_tokens

_LINE_SUFFIX = re.compile(r"^(?P<name>.+?)@L?(?P<line>\d+)$")


class Engine:
    """Index + views + edit gate for one repository root."""

    def __init__(self, root: str, db_path: str | None = None, typecheck: str | None = None,
                 refresh_interval: float = 1.0):
        self.root = os.path.abspath(root)
        if not os.path.isdir(self.root):
            raise FileNotFoundError(f"repository root not found: {self.root}")
        state_dir = os.path.join(self.root, ".dc-engine")
        os.makedirs(state_dir, exist_ok=True)
        ignore = os.path.join(state_dir, ".gitignore")
        if not os.path.exists(ignore):
            with open(ignore, "w") as fh:
                fh.write("*\n")  # keep the index out of the user's git status
        self.store = Store(db_path or os.path.join(state_dir, "index.db"))
        self.indexer = Indexer(self.root, self.store)
        self.checker = Checker(self.root, typecheck)
        self.views = Views(self)
        self.gate = EditGate(self)
        self.refresh_interval = refresh_interval
        self._last_refresh = 0.0
        self.last_refresh_stats: dict[str, int] = {}

    # --- housekeeping ---------------------------------------------------
    def ensure_fresh(self, force: bool = False) -> dict[str, int]:
        now = time.monotonic()
        if force or now - self._last_refresh >= self.refresh_interval:
            self.last_refresh_stats = self.indexer.refresh(force=force)
            self._last_refresh = time.monotonic()
        return self.last_refresh_stats

    def close(self) -> None:
        self.store.close()

    def abspath(self, rel: str) -> str:
        return os.path.join(self.root, rel)

    def module_of(self, rel: str) -> str:
        meta = self.store.get_file(rel)
        return meta.module if meta else module_name(rel)

    def symbol_source(self, sym: Symbol) -> str:
        try:
            with open(self.abspath(sym.path), encoding="utf-8", errors="replace") as fh:
                lines = fh.read().split("\n")
        except OSError:
            return ""
        return "\n".join(lines[sym.start_line - 1: sym.end_line]) + "\n"

    def resolve_ref(self, ref: str) -> tuple[Symbol | None, str | None]:
        """Turn a user/agent reference into exactly one symbol.

        Accepts a full qualname ("shop.billing.charge"), a unique suffix
        ("billing.charge", "Receipt.total"), and an optional "@L<line>"
        to pick between same-named definitions (e.g. property setters).
        """
        ref = (ref or "").strip().strip("`")
        line = None
        m = _LINE_SUFFIX.match(ref)
        if m:
            ref, line = m.group("name"), int(m.group("line"))
        hits = self.store.symbols_by_qualname(ref) or self.store.by_suffix(ref)
        if not hits:
            near = self.store.search(ref.split(".")[-1], 5)
            hint = ("; did you mean: " + ", ".join(s.qualname for s in near)) if near else ""
            return None, f"✗ no symbol '{ref}'{hint}"
        exact = [h for h in hits if h.qualname == ref]
        pool = exact or hits
        if line is not None:
            pick = [h for h in pool if h.start_line <= line <= h.end_line or h.def_line == line]
            if pick:
                return min(pick, key=lambda h: h.end_line - h.start_line), None
            return None, f"✗ no '{ref}' defined at line {line}"
        quals = {h.qualname for h in pool}
        if len(pool) == 1:
            return pool[0], None
        if len(quals) == 1:
            locs = ", ".join(f"{ref}@L{h.def_line}" for h in pool)
            return None, f"✗ '{ref}' is defined {len(pool)} times; pick one: {locs}"
        return None, ("✗ ambiguous '" + ref + "'; candidates: "
                      + ", ".join(sorted(quals)[:10]))

    # --- public API (each call sees an up-to-date index) -----------------
    def repo_map(self, path_prefix: str = "", max_tokens: int = 2000) -> str:
        self.ensure_fresh()
        return self.views.repo_map(path_prefix, max_tokens)

    def find_symbol(self, query: str, limit: int = 15) -> str:
        self.ensure_fresh()
        return self.views.find_symbol(query, limit)

    def get_symbol(self, ref: str, include_body: bool = False) -> str:
        self.ensure_fresh()
        return self.views.get_symbol(ref, include_body)

    def find_references(self, ref: str, limit: int = 40) -> str:
        self.ensure_fresh()
        return self.views.find_references(ref, limit)

    def file_outline(self, path: str) -> str:
        self.ensure_fresh()
        return self.views.file_outline(path)

    def get_slice(self, refs: list[str], depth: int = 1, max_tokens: int = 4000,
                  include_bodies: bool = True) -> str:
        self.ensure_fresh()
        return self.views.get_slice(refs, depth, max_tokens, include_bodies)

    def replace_symbol(self, ref: str, new_code: str, check: bool = True) -> str:
        self.ensure_fresh(force=False)
        return self.gate.replace_symbol(ref, new_code, check)

    def insert_symbol(self, code: str, after: str | None = None, path: str | None = None,
                      check: bool = True) -> str:
        self.ensure_fresh()
        return self.gate.insert_symbol(code, after, path, check)

    def status(self) -> str:
        r = self.ensure_fresh()
        s = self.store.stats()
        internal = s["calls"] - s["external_calls"]
        pct = (100 * s["resolved_calls"] // internal) if internal else 0
        tools = self.checker.available()
        return (f"root: {self.root}\n"
                f"files: {s['files']} ({s['files_with_errors']} with parse errors), {s['lines']} lines, "
                f"~{s['chars'] // 4} tokens if read in full\n"
                f"symbols: {s['symbols']}; call sites: {internal} in-repo ({pct}% resolved statically), "
                f"{s['external_calls']} to external libraries\n"
                f"last refresh: parsed {r.get('parsed', 0)}, unchanged {r.get('unchanged', 0)}, "
                f"removed {r.get('removed', 0)} in {r.get('ms', 0)} ms\n"
                f"checkers: ruff={tools['ruff']}, pyright={tools['pyright']}")

    def full_file_tokens(self, rel: str) -> int:
        meta = self.store.get_file(rel)
        if not meta:
            return 0
        with open(self.abspath(rel), encoding="utf-8", errors="replace") as fh:
            return est_tokens(fh.read())
