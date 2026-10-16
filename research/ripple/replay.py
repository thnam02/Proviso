"""Ripple replay core (feasibility version for sqlglot).

corpus(tree)       SQL inputs the test suite already contains, per dialect: first argument of validate_identity,
                   first argument of validate_all (in the test class's dialect), values of its read={dialect: sql},
                   and parse_one(sql, read=...) literals. Taken from tests/dialects/*.py of the given tree.
ripple(tree)       dialect -> dialects that inherit from it (MySQL -> StarRocks, Doris, SingleStore, ...).
probes(corpus)     each input runs in its own dialect and in every dialect that inherits from that dialect
                   (an edit to MySQL can silently change StarRocks).
run(tree, probes)  behaviour of a source tree on the probes: parse in the dialect, generate in the dialect;
                   an exception is recorded as its type. Runs in a subprocess with only that tree importable.

Usage as a script (inside the subprocess): python replay.py run TREE PROBES.json OUT.json [BASE_OUT.json]
  with BASE_OUT, only probes whose output differs from it are written.
"""

from __future__ import annotations

import ast
import glob
import json
import os
import subprocess
import sys

HERE = os.path.abspath(__file__)


def _dialect_of(cls: ast.ClassDef) -> str | None:
    for node in cls.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "dialect" for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return None


def corpus(tree: str) -> list[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for path in sorted(glob.glob(os.path.join(tree, "tests", "dialects", "test_*.py"))):
        try:
            mod = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        for cls in [n for n in mod.body if isinstance(n, ast.ClassDef)]:
            own = _dialect_of(cls)
            for call in ast.walk(cls):
                if not isinstance(call, ast.Call):
                    continue
                fn = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
                args = call.args
                kw = {k.arg: k.value for k in call.keywords if k.arg}
                first = args[0].value if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str) else None
                if fn in ("validate_identity", "validate_all") and first is not None and own is not None:
                    out.add((own, first))
                if fn == "validate_all" and isinstance(kw.get("read"), ast.Dict):
                    for k, v in zip(kw["read"].keys, kw["read"].values):
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant) and isinstance(v.value, str):
                            out.add((k.value, v.value))
                if fn == "parse_one" and first is not None:
                    rd = kw.get("read") or kw.get("dialect")
                    d = rd.value if isinstance(rd, ast.Constant) else own
                    if d is not None:
                        out.add((d, first))
    return sorted((d, s) for d, s in out if s.strip())


RIPPLE_CODE = r'''
import json, sys
from sqlglot.dialects.dialect import Dialect
cls = Dialect.classes
out = {n: sorted(m for m, c in cls.items() if c is not cls[n] and n and issubclass(c, cls[n])) for n in cls}
print(json.dumps(out))
'''


def _env(tree: str) -> dict:
    return {"PATH": "/usr/bin:/bin", "PYTHONPATH": tree, "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"}


def ripple(tree: str) -> dict[str, list[str]]:
    r = subprocess.run([sys.executable, "-c", RIPPLE_CODE], cwd=tree, env=_env(tree), capture_output=True,
                       text=True, timeout=120)
    return json.loads(r.stdout.strip().splitlines()[-1])


def probes(corp: list[tuple[str, str]], rip: dict[str, list[str]]) -> list[list[str]]:
    """[source dialect, run dialect, sql]"""
    out = []
    for d, s in corp:
        out.append([d, d, s])
        for e in rip.get(d, []):
            out.append([d, e, s])
    return out


def run(tree: str, probes_path: str, out_path: str, base_out: str | None = None, timeout: int = 1800) -> None:
    args = [sys.executable, HERE, "run", tree, probes_path, out_path] + ([base_out] if base_out else [])
    r = subprocess.run(args, cwd=tree, env=_env(tree), capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])


def _main_run(tree: str, probes_path: str, out_path: str, base_out: str | None) -> None:
    import logging
    import warnings
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    sys.setrecursionlimit(5000)
    from sqlglot import parse_one
    ps = json.load(open(probes_path))
    base = json.load(open(base_out)) if base_out else None
    res = {}
    for i, (src, d, sql) in enumerate(ps):
        try:
            v = parse_one(sql, read=d).sql(dialect=d)
        except Exception as e:  # noqa: BLE001
            v = "EXC: " + type(e).__name__
        if base is None or base.get(str(i)) != v:
            res[str(i)] = v
    json.dump(res, open(out_path, "w"))


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "run":
    _main_run(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else None)
