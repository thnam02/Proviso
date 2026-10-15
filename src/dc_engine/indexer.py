"""Incremental indexer and static call resolution.

Files are re-parsed only when their content hash changes. After any
change, call sites are re-resolved against the whole index, because a
new or renamed symbol in one file can change what calls in another file
point to.

Call resolution is static and conservative: it follows module-level
names, imports (including relative imports and package re-exports),
``self``/``cls`` methods through the class hierarchy, and ``super()``.
Calls on values whose type is unknown (``user.notify()``) stay
unresolved and are surfaced separately as name matches, never guessed.
"""

from __future__ import annotations

import builtins
import hashlib
import os
import subprocess
import time
from collections import defaultdict

from .parser import parse_source
from .store import Store

IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", ".env", "node_modules", "__pycache__",
    ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "build", "dist",
    "site-packages", ".dc-engine", ".eggs",
}
MAX_FILE_BYTES = 1_000_000
_BUILTINS = set(dir(builtins))


def list_python_files(root: str) -> list[str]:
    """Repo-relative paths of Python files, honouring .gitignore when in a git repo."""
    if os.path.isdir(os.path.join(root, ".git")):
        try:
            out = subprocess.run(
                ["git", "-C", root, "ls-files", "-co", "--exclude-standard", "-z", "--", "*.py"],
                capture_output=True, check=True, timeout=30,
            ).stdout.decode("utf-8", "replace")
            files = [p for p in out.split("\0") if p]
            return sorted(p for p in files if not (set(p.split("/")) & IGNORE_DIRS)
                          and os.path.isfile(os.path.join(root, p)))
        except (OSError, subprocess.SubprocessError):
            pass
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.endswith(".egg-info")]
        for fn in filenames:
            if fn.endswith(".py"):
                found.append(os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/"))
    return sorted(found)


class Indexer:
    def __init__(self, root: str, store: Store):
        self.root = os.path.abspath(root)
        self.store = store

    def abspath(self, rel: str) -> str:
        return os.path.join(self.root, rel)

    def refresh(self, force: bool = False) -> dict[str, int]:
        """Bring the index up to date. Returns counts of what changed."""
        t0 = time.perf_counter()
        files = list_python_files(self.root)
        known = self.store.file_meta()
        parsed = unchanged = 0
        for rel in files:
            try:
                st = os.stat(self.abspath(rel))
            except OSError:
                continue
            if st.st_size > MAX_FILE_BYTES:
                continue
            meta = known.get(rel)
            if meta and not force and meta.mtime == st.st_mtime and meta.size == st.st_size:
                unchanged += 1
                continue
            if self._index_file(rel, st, meta.hash if (meta and not force) else None):
                parsed += 1
            else:
                unchanged += 1
        removed = [p for p in known if p not in set(files)]
        for rel in removed:
            self.store.delete_file(rel)
        if parsed or removed:
            self.resolve_calls()
        self.store.commit()
        return {"parsed": parsed, "unchanged": unchanged, "removed": len(removed),
                "ms": int((time.perf_counter() - t0) * 1000)}

    def reindex_file(self, rel: str) -> None:
        """Re-index one file immediately (used after an edit)."""
        path = self.abspath(rel)
        if os.path.exists(path):
            self._index_file(rel, os.stat(path), None)
        else:
            self.store.delete_file(rel)
        self.resolve_calls()
        self.store.commit()

    def _index_file(self, rel: str, st: os.stat_result, old_hash: str | None) -> bool:
        with open(self.abspath(rel), "rb") as fh:
            raw = fh.read()
        digest = hashlib.sha1(raw).hexdigest()
        if old_hash == digest:
            self.store.touch_file(rel, st.st_mtime, st.st_size)
            return False
        text = raw.decode("utf-8", "replace")
        self.store.replace_file(parse_source(text, rel), digest, st.st_mtime, st.st_size, len(text))
        return True

    # --- call resolution -------------------------------------------------
    def resolve_calls(self) -> None:
        symbols = self.store.all_symbols()
        quals = {s.qualname for s in symbols}
        kinds = {s.qualname: s.kind for s in symbols}
        sym_module: dict[str, str] = {}
        enclosing_class: dict[str, str | None] = {}
        modules = {m.module for m in self.store.file_meta().values()}
        path_module = {p: m.module for p, m in self.store.file_meta().items()}
        for s in symbols:
            sym_module[s.qualname] = path_module.get(s.path, "")
            enclosing_class[s.qualname] = s.parent if s.kind == "method" else None

        imports: dict[str, dict[str, tuple[str, bool]]] = defaultdict(dict)
        stars: dict[str, list[str]] = defaultdict(list)
        for row in self.store.all_imports():
            if row["alias"] == "*":
                stars[row["module"]].append(row["target"])
            else:
                imports[row["module"]].setdefault(row["alias"], (row["target"], bool(row["is_module"])))

        r = _Resolver(quals, kinds, modules, imports, stars)
        # Resolve class bases first so method lookups can walk the hierarchy.
        for s in symbols:
            if s.kind == "class":
                mod = sym_module[s.qualname]
                r.bases[s.qualname] = [b for b in (r.resolve(mod, None, e, want_class=True)
                                                   for e in s.bases) if b and kinds.get(b) == "class"]
                r.ext_bases[s.qualname] = [x for x in (r.external(mod, e) for e in s.bases) if x]
        updates, drop = [], []
        for row in self.store.all_calls():
            caller, expr = row["caller"], row["expr"]
            module = sym_module.get(caller, "")
            callee = r.resolve(module, enclosing_class.get(caller), expr)
            if callee:
                updates.append((callee, None, row["rowid"]))
                continue
            external = r.external(module, expr, enclosing_class.get(caller))
            if external:
                updates.append((None, external, row["rowid"]))
            elif r.is_builtin(module, expr):
                drop.append(row["rowid"])  # print(), len(), super() ... carry no signal
            else:
                updates.append((None, None, row["rowid"]))
        self.store.set_callees(updates, drop)


class _Resolver:
    def __init__(self, quals, kinds, modules, imports, stars=None):
        self.quals: set[str] = quals
        self.kinds: dict[str, str] = kinds
        self.modules: set[str] = modules
        self.imports: dict[str, dict[str, tuple[str, bool]]] = imports
        self.stars: dict[str, list[str]] = stars or {}
        self.bases: dict[str, list[str]] = {}
        self.ext_bases: dict[str, list[str]] = {}

    def external_base(self, cls: str, seen: set[str] | None = None) -> str | None:
        """First base class outside the repo anywhere in `cls`'s hierarchy."""
        seen = seen or set()
        if cls in seen:
            return None
        seen.add(cls)
        if self.ext_bases.get(cls):
            return self.ext_bases[cls][0]
        for base in self.bases.get(cls, []):
            hit = self.external_base(base, seen)
            if hit:
                return hit
        return None

    def via_star(self, module: str, name: str, depth: int) -> str | None:
        """Look `name` up through `from x import *` statements in `module`."""
        if depth > 6:
            return None
        for src in self.stars.get(module, []):
            hit = self.follow(f"{src}.{name}", depth + 1)
            if hit:
                return hit
        return None

    def follow(self, target: str, depth: int = 0) -> str | None:
        """Resolve a fully qualified name, following package re-exports."""
        if target in self.quals or target in self.modules:
            return target
        if depth > 6:
            return None
        mod, _, name = target.rpartition(".")
        if mod in self.modules and name in self.imports.get(mod, {}):
            return self.follow(self.imports[mod][name][0], depth + 1)
        if mod in self.modules:
            hit = self.via_star(mod, name, depth)
            if hit:
                return hit
        # `import a.b` style chains: a.b.c where a.b is a module re-exporting c
        if mod and mod not in self.modules:
            head = self.follow(mod, depth + 1)
            if head and head != mod:
                return self.follow(f"{head}.{name}", depth + 1)
        return None

    def lookup_member(self, cls: str, member: str, seen: set[str] | None = None) -> str | None:
        seen = seen or set()
        if cls in seen:
            return None
        seen.add(cls)
        cand = f"{cls}.{member}"
        if cand in self.quals:
            return cand
        for base in self.bases.get(cls, []):
            hit = self.lookup_member(base, member, seen)
            if hit:
                return hit
        return None

    def name_in_module(self, module: str, name: str) -> str | None:
        local = f"{module}.{name}" if module else name
        if local in self.quals:
            return local
        imp = self.imports.get(module, {}).get(name)
        if imp:
            # Keep module imports even when the package has no __init__.py
            # (namespace package), so `a.b.f()` can still walk down to a.b.
            return self.follow(imp[0]) or (imp[0] if imp[1] else None)
        if name in self.modules:
            return name
        return self.via_star(module, name, 0)

    def external(self, module: str, expr: str, cls: str | None = None) -> str | None:
        """If `expr` goes through an import that leaves the repo, name its target."""
        head, _, rest = expr.partition(".")
        if cls and head in ("self", "cls", "super()") and rest and "." not in rest:
            base = self.external_base(cls)  # e.g. super().invoke on a click.Group subclass
            return f"{base}.{rest}" if base else None
        imp = self.imports.get(module, {}).get(head)
        if not imp:
            return None
        target = imp[0]
        if self.follow(target):
            return None  # in-repo, just not resolvable further (e.g. attribute)
        return f"{target}.{rest}" if rest else target

    def is_builtin(self, module: str, expr: str) -> bool:
        if "." in expr:
            return False
        if f"{module}.{expr}" in self.quals or expr in self.imports.get(module, {}):
            return False
        return expr in _BUILTINS

    def resolve(self, module: str, cls: str | None, expr: str, want_class: bool = False) -> str | None:
        if not expr or expr.startswith("?"):
            return None
        parts = expr.split(".")
        head = parts[0]
        if head == "super()":
            if not cls or len(parts) != 2:
                return None
            for base in self.bases.get(cls, []):
                hit = self.lookup_member(base, parts[1])
                if hit:
                    return hit
            return None
        if head in ("self", "cls"):
            if cls and expr == "cls":
                return cls  # cls(...) constructs the enclosing class
            if cls and len(parts) == 2:
                return self.lookup_member(cls, parts[1])
            return None
        cur = self.name_in_module(module, head)
        if cur is None:
            return None
        for part in parts[1:]:
            if self.kinds.get(cur) == "class":
                nxt = self.lookup_member(cur, part)
            else:
                nxt = self.follow(f"{cur}.{part}")
            if nxt is None:
                return None
            cur = nxt
        if cur in self.quals:
            return cur
        return cur if want_class else None
