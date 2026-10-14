"""Command-line access to the engine, for trying it out and for benchmarks.

    dc-engine status
    dc-engine map [--prefix shop/] [--max-tokens 2000]
    dc-engine find charge
    dc-engine show billing.charge [--body]
    dc-engine refs User.notify
    dc-engine slice billing.charge [more targets] [--depth 1] [--max-tokens 4000]
    dc-engine outline shop/billing.py
    dc-engine replace billing.charge new_code.py      (or '-' for stdin)
    dc-engine bench billing.charge [more targets]
"""

from __future__ import annotations

import argparse
import os
import sys

from .engine import Engine
from .views import est_tokens


def _bench(engine: Engine, targets: list[str], depth: int, max_tokens: int) -> str:
    """Compare slice size with the naive alternative: reading every file that
    contains a target or one of its direct callees/callers."""
    engine.ensure_fresh()
    files: set[str] = set()
    names = []
    for ref in targets:
        sym, err = engine.resolve_ref(ref)
        if err:
            return err
        names.append(sym.qualname)
        files.add(sym.path)
        for row in engine.store.callees_of(sym.qualname):
            if row["callee"]:
                for s in engine.store.symbols_by_qualname(row["callee"]):
                    files.add(s.path)
        for row in engine.store.callers_of(sym.qualname):
            files.add(row["path"])
    full = sum(engine.full_file_tokens(f) for f in files)
    slice_text = engine.get_slice(targets, depth=depth, max_tokens=max_tokens)
    st = engine.store.stats()
    repo_tokens = st["chars"] // 4
    map_tokens = est_tokens(engine.repo_map(max_tokens=10**9))
    lines = [
        f"targets: {', '.join(names)}",
        f"naive: read {len(files)} file(s) = ~{full:,} tokens",
        f"dc_get_slice (depth {depth}) = ~{est_tokens(slice_text):,} tokens "
        f"({100 - 100 * est_tokens(slice_text) // max(full, 1)}% fewer)",
        f"whole repo = ~{repo_tokens:,} tokens; full-signature repo map = ~{map_tokens:,} tokens "
        f"({100 - 100 * map_tokens // max(repo_tokens, 1)}% fewer)",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="dc-engine", description="Symbol-level code context for agents.")
    p.add_argument("--root", default=os.environ.get("DC_ROOT", os.getcwd()))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    m = sub.add_parser("map"); m.add_argument("--prefix", default=""); m.add_argument("--max-tokens", type=int, default=2000)
    f = sub.add_parser("find"); f.add_argument("query"); f.add_argument("--limit", type=int, default=15)
    s = sub.add_parser("show"); s.add_argument("name"); s.add_argument("--body", action="store_true")
    r = sub.add_parser("refs"); r.add_argument("name")
    sl = sub.add_parser("slice"); sl.add_argument("targets", nargs="+")
    sl.add_argument("--depth", type=int, default=1); sl.add_argument("--max-tokens", type=int, default=4000)
    sl.add_argument("--no-bodies", action="store_true")
    o = sub.add_parser("outline"); o.add_argument("path")
    rp = sub.add_parser("replace"); rp.add_argument("name"); rp.add_argument("code_file")
    rp.add_argument("--no-check", action="store_true")
    b = sub.add_parser("bench"); b.add_argument("targets", nargs="+")
    b.add_argument("--depth", type=int, default=1); b.add_argument("--max-tokens", type=int, default=4000)
    a = p.parse_args(argv)

    e = Engine(a.root)
    if a.cmd == "status":
        out = e.status()
    elif a.cmd == "map":
        out = e.repo_map(a.prefix, a.max_tokens)
    elif a.cmd == "find":
        out = e.find_symbol(a.query, a.limit)
    elif a.cmd == "show":
        out = e.get_symbol(a.name, a.body)
    elif a.cmd == "refs":
        out = e.find_references(a.name)
    elif a.cmd == "slice":
        out = e.get_slice(a.targets, a.depth, a.max_tokens, not a.no_bodies)
    elif a.cmd == "outline":
        out = e.file_outline(a.path)
    elif a.cmd == "replace":
        code = sys.stdin.read() if a.code_file == "-" else open(a.code_file, encoding="utf-8").read()
        out = e.replace_symbol(a.name, code, check=not a.no_check)
    else:
        out = _bench(e, a.targets, a.depth, a.max_tokens)
    print(out)


if __name__ == "__main__":
    main()
