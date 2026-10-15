"""Symbol-level edits with instant, diffed feedback.

Agents edit by naming a symbol and supplying its full new definition,
instead of string search-and-replace. The gate:

1. re-parses the current file to find the symbol's exact range
   (decorators included),
2. re-indents the new code to the symbol's original column,
3. rejects the edit without touching the file if the result does not parse,
4. writes atomically, re-indexes, and reports only diagnostics the edit
   introduced, plus warnings about callers a signature change may break.

Limitation: re-indentation shifts the content of multi-line string
literals inside the new code, as any editor-level re-indent would.
"""

from __future__ import annotations

import ast
import hashlib
import os
import tempfile
import textwrap
from typing import TYPE_CHECKING

from .checks import CheckResult, diff_diags
from .parser import Symbol, class_signature, function_signature, parse_source

if TYPE_CHECKING:
    from .engine import Engine

MAX_REPORTED_DIAGS = 10


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def _indent(code: str, col: int) -> str:
    pad = " " * col
    return "\n".join((pad + ln) if ln.strip() else "" for ln in code.split("\n"))


def _normalise(code: str) -> str:
    code = code.replace("\r\n", "\n").expandtabs(4)
    return textwrap.dedent(code).strip("\n")


def _atomic_write(path: str, text: str) -> None:
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".dc-edit-", suffix=".py")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        if os.path.exists(path):
            os.chmod(tmp, os.stat(path).st_mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _signature_of(node: ast.stmt) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return function_signature(node)
    if isinstance(node, ast.ClassDef):
        return class_signature(node)
    return None


def _params_only(sig: str) -> str:
    """Strip decorators so that only the def line is compared."""
    i = sig.find("def ")
    j = sig.find("class ")
    k = min(x for x in (i, j) if x >= 0) if (i >= 0 or j >= 0) else 0
    return sig[k:]


class EditGate:
    def __init__(self, engine: Engine):
        self.e = engine

    # ------------------------------------------------------------------
    def _current_symbol(self, sym: Symbol, source: str) -> Symbol | None:
        """Find the symbol in the file as it is on disk right now."""
        fresh = parse_source(source, sym.path)
        same = [s for s in fresh.symbols if s.qualname == sym.qualname]
        if not same:
            return None
        return min(same, key=lambda s: abs(s.def_line - sym.def_line))

    def _checks(self, rel: str, before_text: str, after_text: str, check: bool,
                before_result: CheckResult | None) -> list[str]:
        if not check:
            return ["checks: skipped (check=false)"]
        after = self.e.checker.run(rel, after_text, _sha1(after_text), on_disk=True)
        before = before_result
        parts = ["syntax ok"]
        new_all = []
        for tool in after.ran:
            b = [d for d in (before.diags if before else []) if d.tool == tool]
            a = [d for d in after.diags if d.tool == tool]
            if before is None or tool not in before.ran:
                parts.append(f"{tool}: {len(a)} issue(s) in file (no baseline)")
                new_all += a
                continue
            new, fixed = diff_diags(b, a)
            label = f"{len(new)} new" if new else "no new issues"
            if fixed:
                label += f", {fixed} fixed"
            parts.append(f"{tool}: {label}")
            new_all += new
        for tool, why in after.skipped.items():
            parts.append(f"{tool}: skipped ({why})")
        lines = ["checks: " + " · ".join(parts)]
        for d in sorted(new_all, key=lambda d: d.line)[:MAX_REPORTED_DIAGS]:
            lines.append("  " + d.render())
        if len(new_all) > MAX_REPORTED_DIAGS:
            lines.append(f"  … +{len(new_all) - MAX_REPORTED_DIAGS} more")
        return lines

    def _baseline(self, rel: str, text: str, check: bool) -> CheckResult | None:
        if not check:
            return None
        return self.e.checker.run(rel, text, _sha1(text), on_disk=True)

    def _caller_files(self, sym: Symbol, limit: int = 25) -> list[str]:
        """Other files that call `sym`, resolved or plausibly (same method name).

        Name matches over-approximate, which only costs check time: results
        are diffed before/after, so unrelated files add no noise. Library
        files are checked before tests when the list must be capped."""
        files = {r["path"] for r in self.e.store.callers_of(sym.qualname)}
        files |= {r["path"] for r in self.e.store.unresolved_mentions(sym.name)
                  if r["expr"].split(".")[-1] == sym.name}
        files.discard(sym.path)
        is_test = lambda f: f.startswith("tests/") or "/tests/" in f or f.split("/")[-1].startswith("test_")
        return sorted(files, key=lambda f: (is_test(f), f))[:limit]

    # ------------------------------------------------------------------
    def replace_symbol(self, ref: str, new_code: str, check: bool = True) -> str:
        sym, err = self.e.resolve_ref(ref)
        if err:
            return err
        path = self.e.abspath(sym.path)
        with open(path, encoding="utf-8", newline="") as fh:
            source = fh.read()
        newline = "\r\n" if "\r\n" in source else "\n"
        current = self._current_symbol(sym, source.replace("\r\n", "\n"))
        if current is None:
            return f"✗ {sym.qualname} no longer exists in {sym.path}; run dc_file_outline."

        code = _normalise(new_code)
        if not code:
            return "✗ rejected: new_code is empty (to delete a symbol, use your normal edit tool)."
        try:
            parsed = ast.parse(code)
        except SyntaxError as exc:
            return f"✗ rejected (file unchanged): new_code has SyntaxError at line {exc.lineno}: {exc.msg}"
        defs = [n for n in parsed.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        if len(parsed.body) != 1 or len(defs) != 1:
            return ("✗ rejected (file unchanged): new_code must contain exactly one def/class "
                    "(the full new definition of the symbol, decorators included). "
                    "Use dc_insert_symbol to add new definitions.")
        new_node = defs[0]

        lines = source.replace("\r\n", "\n").split("\n")
        start, end = current.start_line, current.end_line
        new_lines = lines[: start - 1] + _indent(code, current.col).split("\n") + lines[end:]
        new_source = "\n".join(new_lines)
        try:
            ast.parse(new_source)
        except SyntaxError as exc:
            return (f"✗ rejected (file unchanged): result would not parse — "
                    f"SyntaxError at L{exc.lineno}: {exc.msg}")

        # If the signature changes, callers elsewhere may break. Type-check the
        # files that call it (resolved or matched by name) before and after.
        new_sig_full = _signature_of(new_node) or ""
        sig_changed = (current.kind != "class" and new_node.name == current.name
                       and _params_only(current.signature) != _params_only(new_sig_full))
        caller_files = self._caller_files(sym) if (check and sig_changed) else []
        caller_before = self.e.checker.pyright_files(caller_files) if caller_files else None

        baseline = self._baseline(sym.path, source, check)
        _atomic_write(path, new_source.replace("\n", newline) if newline != "\n" else new_source)
        self.e.indexer.reindex_file(sym.path)

        new_end = start + len(code.split("\n")) - 1
        out = [f"✓ replaced {sym.qualname}  {sym.path} L{start}-{end} → L{start}-{new_end}"]
        out += self._checks(sym.path, source, new_source, check, baseline)

        if caller_before is not None:
            caller_after = self.e.checker.pyright_files(caller_files) or {}
            broken: list = []
            for f in caller_files:
                new, _ = diff_diags(caller_before.get(f, []), caller_after.get(f, []))
                broken += new
            if broken:
                out.append(f"✗ breaks {len(broken)} call site(s) in other files (pyright):")
                out += ["  " + d.render() for d in broken[:MAX_REPORTED_DIAGS]]
            else:
                out.append(f"other files checked for broken callers: {len(caller_files)} — no new errors")

        # Contract-ish warnings: renames and signature changes with live callers.
        callers = sorted({(r["caller"], r["path"], r["line"]) for r in self.e.store.callers_of(sym.qualname)})
        if new_node.name != current.name:
            out.append(f"⚠ renamed {current.name} → {new_node.name}; "
                       f"{len(callers)} caller(s) still use the old name")
        else:
            old_sig, new_sig = _params_only(current.signature), _params_only(_signature_of(new_node) or "")
            if old_sig != new_sig and callers and current.kind != "class":
                out.append(f"⚠ signature changed: {old_sig}  →  {new_sig}")
                out.append(f"  {len(callers)} caller(s) may need updating:")
                out += [f"    {c}  {p}:L{ln}" for c, p, ln in callers[:8]]
                if len(callers) > 8:
                    out.append(f"    … +{len(callers) - 8} more (dc_find_references)")
        return "\n".join(out)

    # ------------------------------------------------------------------
    def insert_symbol(self, code: str, after: str | None = None, path: str | None = None,
                      check: bool = True) -> str:
        if not after and not path:
            return "✗ give either after=<symbol> (insert after it, same indentation) or path=<file> (append)."
        code = _normalise(code)
        try:
            parsed = ast.parse(code)
        except SyntaxError as exc:
            return f"✗ rejected (file unchanged): code has SyntaxError at line {exc.lineno}: {exc.msg}"
        if not parsed.body:
            return "✗ rejected: code is empty."

        if after:
            anchor, err = self.e.resolve_ref(after)
            if err:
                return err
            rel = anchor.path
        else:
            rel = path.lstrip("./")
            anchor = None
        abspath = self.e.abspath(rel)
        exists = os.path.exists(abspath)
        source = ""
        if exists:
            with open(abspath, encoding="utf-8", newline="") as fh:
                source = fh.read()
        newline = "\r\n" if "\r\n" in source else "\n"
        text = source.replace("\r\n", "\n")
        lines = text.split("\n") if text else []

        if anchor is not None:
            current = self._current_symbol(anchor, text)
            if current is None:
                return f"✗ {anchor.qualname} no longer exists in {rel}."
            col, at = current.col, current.end_line
            gap = 2 if col == 0 else 1
            block = [""] * gap + _indent(code, col).split("\n")
            new_lines = lines[:at] + block + lines[at:]
        else:
            while lines and lines[-1] == "":
                lines.pop()
            block = ([""] * 2 if lines else []) + code.split("\n")
            new_lines = lines + block + [""]
        new_source = "\n".join(new_lines)
        try:
            ast.parse(new_source)
        except SyntaxError as exc:
            return f"✗ rejected (file unchanged): result would not parse — SyntaxError at L{exc.lineno}: {exc.msg}"

        baseline = self._baseline(rel, source, check) if exists else None
        os.makedirs(os.path.dirname(abspath) or ".", exist_ok=True)
        _atomic_write(abspath, new_source.replace("\n", newline) if newline != "\n" else new_source)
        self.e.indexer.reindex_file(rel)

        added = [n.name for n in parsed.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        where = f"after {anchor.qualname}" if anchor else f"at end of {rel}"
        out = [f"✓ inserted {', '.join(added) or f'{len(parsed.body)} statement(s)'} {where}"]
        out += self._checks(rel, source, new_source, check, baseline)
        return "\n".join(out)
