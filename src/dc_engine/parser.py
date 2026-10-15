"""Extract symbols, imports and call sites from Python source.

Uses the standard-library ``ast`` module, which gives exact line and
column ranges for Python. The rest of the engine only depends on the
dataclasses below, so a tree-sitter backend (for TypeScript and other
languages) can be added behind the same interface later.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

MAX_SIGNATURE_CHARS = 240


@dataclass
class Symbol:
    qualname: str          # e.g. "shop.billing.Receipt.total"
    name: str              # e.g. "total"
    kind: str              # "function" | "method" | "class"
    path: str              # repo-relative path
    start_line: int        # first line, including decorators
    def_line: int          # line of the def/class keyword
    end_line: int          # last line of the body
    col: int               # indentation column of the def/class keyword
    signature: str
    docstring: str | None
    parent: str | None     # enclosing class qualname for methods / nested classes
    bases: list[str] = field(default_factory=list)  # raw base-class expressions


@dataclass
class ImportRec:
    module: str        # module doing the import
    alias: str         # local name bound by the import
    target: str        # fully qualified target (module, or module.name)
    is_module: bool    # True for `import x`, False for `from x import y`


@dataclass
class CallRec:
    caller: str        # qualname of the enclosing function/method
    expr: str          # callee expression, e.g. "charge", "self.helper", "tax.compute"
    line: int


@dataclass
class ParsedFile:
    path: str
    module: str
    symbols: list[Symbol]
    imports: list[ImportRec]
    calls: list[CallRec]
    module_doc: str | None
    line_count: int
    error: str | None = None


def module_name(relpath: str) -> str:
    """Map a repo-relative path to a dotted module name.

    ``src/pkg/mod.py`` -> ``pkg.mod``; ``pkg/__init__.py`` -> ``pkg``.
    """
    parts = relpath.replace("\\", "/").split("/")
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if len(parts) > 1 and parts[0] == "src":
        parts = parts[1:]
    if len(parts) > 1 and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _shorten(text: str, limit: int = MAX_SIGNATURE_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _decorators(node: ast.AST) -> str:
    decos = getattr(node, "decorator_list", [])
    return " ".join("@" + ast.unparse(d) for d in decos)


def function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    kw = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    sig = f"{kw} {node.name}({ast.unparse(node.args)}){ret}"
    decos = _decorators(node)
    return _shorten(f"{decos} {sig}" if decos else sig)


def class_signature(node: ast.ClassDef) -> str:
    args = [ast.unparse(b) for b in node.bases] + [ast.unparse(k) for k in node.keywords]
    sig = f"class {node.name}({', '.join(args)})" if args else f"class {node.name}"
    decos = _decorators(node)
    return _shorten(f"{decos} {sig}" if decos else sig)


def call_expr(func: ast.AST) -> str | None:
    """Render the callee of a Call node as a dotted string.

    ``foo()`` -> "foo", ``a.b.c()`` -> "a.b.c", ``super().m()`` -> "super().m",
    ``make().m()`` -> "?.m" (receiver unknown, kept for name-based matching).
    """
    parts: list[str] = []
    node = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "super":
        parts.append("super()")
    elif parts:
        parts.append("?")
    else:
        return None
    return ".".join(reversed(parts))


def _relative_base(module: str, is_package: bool, level: int) -> str:
    package = module if is_package else module.rpartition(".")[0]
    parts = package.split(".") if package else []
    if level > 1:
        parts = parts[: len(parts) - (level - 1)]
    return ".".join(parts)


class _Collector:
    def __init__(self, path: str, module: str, is_package: bool):
        self.path = path
        self.module = module
        self.is_package = is_package
        self.symbols: list[Symbol] = []
        self.imports: list[ImportRec] = []
        self.calls: list[CallRec] = []

    # --- imports -------------------------------------------------------
    def add_import(self, node: ast.Import | ast.ImportFrom) -> None:
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    self.imports.append(ImportRec(self.module, a.asname, a.name, True))
                else:
                    # `import a.b.c` binds `a`; record the full path too so
                    # `a.b.c.f()` can be resolved from the head name.
                    head = a.name.split(".")[0]
                    self.imports.append(ImportRec(self.module, head, head, True))
            return
        if node.level:
            base = _relative_base(self.module, self.is_package, node.level)
            src = ".".join(p for p in (base, node.module or "") if p)
        else:
            src = node.module or ""
        for a in node.names:
            if a.name == "*":
                # Star import: recorded with alias "*" and followed at resolve time.
                self.imports.append(ImportRec(self.module, "*", src, True))
                continue
            target = f"{src}.{a.name}" if src else a.name
            self.imports.append(ImportRec(self.module, a.asname or a.name, target, False))

    # --- definitions ---------------------------------------------------
    def visit_block(self, stmts: list[ast.stmt], prefix: str, parent: str | None) -> None:
        for node in stmts:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if parent is None:
                    self.add_import(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.add_function(node, prefix, parent)
            elif isinstance(node, ast.ClassDef):
                self.add_class(node, prefix, parent)
            elif isinstance(node, (ast.If, ast.Try, ast.With, ast.AsyncWith)) or (
                hasattr(ast, "TryStar") and isinstance(node, ast.TryStar)
            ):
                # Definitions guarded by `if TYPE_CHECKING:` / try-except / etc.
                for block in ("body", "orelse", "finalbody"):
                    self.visit_block(getattr(node, block, []) or [], prefix, parent)
                for handler in getattr(node, "handlers", []) or []:
                    self.visit_block(handler.body, prefix, parent)

    def _range(self, node: ast.AST) -> tuple[int, int, int]:
        decos = getattr(node, "decorator_list", [])
        start = min([d.lineno for d in decos] + [node.lineno])
        return start, node.lineno, node.end_lineno or node.lineno

    def add_function(self, node, prefix: str, parent: str | None) -> None:
        qual = f"{prefix}.{node.name}"
        start, def_line, end = self._range(node)
        self.symbols.append(Symbol(
            qualname=qual, name=node.name,
            kind="method" if parent else "function",
            path=self.path, start_line=start, def_line=def_line, end_line=end,
            col=node.col_offset, signature=function_signature(node),
            docstring=ast.get_docstring(node), parent=parent,
        ))
        seen: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Import, ast.ImportFrom)):
                # Function-local imports are treated as module-level for
                # resolution purposes (a safe over-approximation).
                self.add_import(sub)
            elif isinstance(sub, ast.Call):
                expr = call_expr(sub.func)
                if expr and expr not in seen:
                    seen.add(expr)
                    self.calls.append(CallRec(qual, expr, sub.lineno))

    def add_class(self, node: ast.ClassDef, prefix: str, parent: str | None) -> None:
        qual = f"{prefix}.{node.name}"
        start, def_line, end = self._range(node)
        self.symbols.append(Symbol(
            qualname=qual, name=node.name, kind="class",
            path=self.path, start_line=start, def_line=def_line, end_line=end,
            col=node.col_offset, signature=class_signature(node),
            docstring=ast.get_docstring(node), parent=parent,
            bases=[ast.unparse(b) for b in node.bases],
        ))
        self.visit_block(node.body, qual, qual)


def parse_source(source: str, path: str) -> ParsedFile:
    module = module_name(path)
    is_package = path.replace("\\", "/").endswith("__init__.py")
    line_count = source.count("\n") + (0 if source.endswith("\n") or not source else 1)
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError) as exc:
        lineno = getattr(exc, "lineno", None)
        msg = f"{type(exc).__name__}: {getattr(exc, 'msg', exc)}" + (f" (line {lineno})" if lineno else "")
        return ParsedFile(path, module, [], [], [], None, line_count, error=msg)
    col = _Collector(path, module, is_package)
    col.visit_block(tree.body, module, None)
    return ParsedFile(path, module, col.symbols, col.imports, col.calls,
                      ast.get_docstring(tree), line_count)
