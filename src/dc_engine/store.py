"""SQLite storage for the code index."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass

from .parser import ParsedFile, Symbol

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY, module TEXT, hash TEXT, mtime REAL, size INTEGER,
    lines INTEGER, chars INTEGER, error TEXT, doc TEXT
);
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY, qualname TEXT, name TEXT, kind TEXT, path TEXT,
    start_line INTEGER, def_line INTEGER, end_line INTEGER, col INTEGER,
    signature TEXT, docstring TEXT, parent TEXT, bases TEXT
);
CREATE INDEX IF NOT EXISTS sym_qual ON symbols(qualname);
CREATE INDEX IF NOT EXISTS sym_name ON symbols(name);
CREATE INDEX IF NOT EXISTS sym_path ON symbols(path);
CREATE TABLE IF NOT EXISTS imports (
    module TEXT, alias TEXT, target TEXT, is_module INTEGER, path TEXT
);
CREATE INDEX IF NOT EXISTS imp_module ON imports(module);
CREATE TABLE IF NOT EXISTS calls (
    caller TEXT, expr TEXT, line INTEGER, path TEXT, callee TEXT, external TEXT
);
CREATE INDEX IF NOT EXISTS call_caller ON calls(caller);
CREATE INDEX IF NOT EXISTS call_callee ON calls(callee);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

SCHEMA_VERSION = "3"  # bump whenever parser output changes


@dataclass
class FileMeta:
    path: str
    module: str
    hash: str
    mtime: float
    size: int
    lines: int
    chars: int
    error: str | None
    doc: str | None


def _row_to_symbol(row: sqlite3.Row) -> Symbol:
    return Symbol(
        qualname=row["qualname"], name=row["name"], kind=row["kind"], path=row["path"],
        start_line=row["start_line"], def_line=row["def_line"], end_line=row["end_line"],
        col=row["col"], signature=row["signature"], docstring=row["docstring"],
        parent=row["parent"], bases=json.loads(row["bases"] or "[]"),
    )


class Store:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        cur = self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        if cur is None or cur["value"] != SCHEMA_VERSION:
            self.db.executescript(
                "DELETE FROM files; DELETE FROM symbols; DELETE FROM imports; DELETE FROM calls;")
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)", (SCHEMA_VERSION,))
            self.db.commit()

    # --- files ---------------------------------------------------------
    def file_meta(self) -> dict[str, FileMeta]:
        rows = self.db.execute("SELECT * FROM files").fetchall()
        return {r["path"]: FileMeta(**dict(r)) for r in rows}

    def get_file(self, path: str) -> FileMeta | None:
        r = self.db.execute("SELECT * FROM files WHERE path=?", (path,)).fetchone()
        return FileMeta(**dict(r)) if r else None

    def touch_file(self, path: str, mtime: float, size: int) -> None:
        self.db.execute("UPDATE files SET mtime=?, size=? WHERE path=?", (mtime, size, path))

    def replace_file(self, pf: ParsedFile, digest: str, mtime: float, size: int, chars: int) -> None:
        self.delete_file(pf.path)
        self.db.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?)",
            (pf.path, pf.module, digest, mtime, size, pf.line_count, chars, pf.error, pf.module_doc),
        )
        self.db.executemany(
            "INSERT INTO symbols (qualname,name,kind,path,start_line,def_line,end_line,col,"
            "signature,docstring,parent,bases) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(s.qualname, s.name, s.kind, s.path, s.start_line, s.def_line, s.end_line, s.col,
              s.signature, s.docstring, s.parent, json.dumps(s.bases)) for s in pf.symbols],
        )
        self.db.executemany(
            "INSERT INTO imports VALUES (?,?,?,?,?)",
            [(i.module, i.alias, i.target, int(i.is_module), pf.path) for i in pf.imports],
        )
        self.db.executemany(
            "INSERT INTO calls VALUES (?,?,?,?,NULL,NULL)",
            [(c.caller, c.expr, c.line, pf.path) for c in pf.calls],
        )

    def delete_file(self, path: str) -> None:
        for table in ("files", "symbols", "imports", "calls"):
            self.db.execute(f"DELETE FROM {table} WHERE path=?", (path,))

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # --- symbols -------------------------------------------------------
    def all_symbols(self) -> list[Symbol]:
        rows = self.db.execute("SELECT * FROM symbols ORDER BY path, start_line").fetchall()
        return [_row_to_symbol(r) for r in rows]

    def symbols_by_qualname(self, qualname: str) -> list[Symbol]:
        rows = self.db.execute(
            "SELECT * FROM symbols WHERE qualname=? ORDER BY path, def_line", (qualname,)).fetchall()
        return [_row_to_symbol(r) for r in rows]

    def symbols_in_file(self, path: str) -> list[Symbol]:
        rows = self.db.execute(
            "SELECT * FROM symbols WHERE path=? ORDER BY start_line", (path,)).fetchall()
        return [_row_to_symbol(r) for r in rows]

    def children(self, parent: str) -> list[Symbol]:
        rows = self.db.execute(
            "SELECT * FROM symbols WHERE parent=? ORDER BY def_line", (parent,)).fetchall()
        return [_row_to_symbol(r) for r in rows]

    def search(self, query: str, limit: int) -> list[Symbol]:
        q = query.strip()
        rows = self.db.execute(
            """SELECT *, CASE
                 WHEN name = :q THEN 0
                 WHEN qualname = :q OR qualname LIKE '%.' || :q THEN 1
                 WHEN name LIKE :q || '%' THEN 2
                 ELSE 3 END AS rank
               FROM symbols
               WHERE name LIKE '%' || :q || '%' OR qualname LIKE '%' || :q || '%'
               ORDER BY rank, length(qualname), qualname LIMIT :lim""",
            {"q": q, "lim": limit},
        ).fetchall()
        return [_row_to_symbol(r) for r in rows]

    def by_suffix(self, suffix: str) -> list[Symbol]:
        rows = self.db.execute(
            "SELECT * FROM symbols WHERE qualname=? OR qualname LIKE ? ORDER BY length(qualname)",
            (suffix, "%." + suffix)).fetchall()
        return [_row_to_symbol(r) for r in rows]

    # --- imports & calls ----------------------------------------------
    def all_imports(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM imports").fetchall()

    def all_calls(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT rowid, * FROM calls").fetchall()

    def set_callees(self, updates: list[tuple[str | None, str | None, int]],
                    drop: list[int] | None = None) -> None:
        self.db.executemany("UPDATE calls SET callee=?, external=? WHERE rowid=?", updates)
        if drop:
            self.db.executemany("DELETE FROM calls WHERE rowid=?", [(r,) for r in drop])

    def callees_of(self, caller: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM calls WHERE caller=? ORDER BY line", (caller,)).fetchall()

    def callers_of(self, callee: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM calls WHERE callee=? ORDER BY path, line", (callee,)).fetchall()

    def unresolved_mentions(self, name: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM calls WHERE callee IS NULL AND external IS NULL AND (expr=? OR expr LIKE ?) "
            "ORDER BY path, line",
            (name, "%." + name)).fetchall()

    def stats(self) -> dict[str, int]:
        q = lambda sql: self.db.execute(sql).fetchone()[0]
        return {
            "files": q("SELECT count(*) FROM files"),
            "files_with_errors": q("SELECT count(*) FROM files WHERE error IS NOT NULL"),
            "symbols": q("SELECT count(*) FROM symbols"),
            "calls": q("SELECT count(*) FROM calls"),
            "resolved_calls": q("SELECT count(*) FROM calls WHERE callee IS NOT NULL"),
            "external_calls": q("SELECT count(*) FROM calls WHERE external IS NOT NULL"),
            "lines": q("SELECT coalesce(sum(lines),0) FROM files"),
            "chars": q("SELECT coalesce(sum(chars),0) FROM files"),
        }
