"""Command-line access to the engine, for trying it out and for benchmarks.

    dc-engine status
    dc-engine map [--prefix shop/] [--max-tokens 800]
    dc-engine find charge
    dc-engine show billing.charge [--body]
    dc-engine refs User.notify
    dc-engine slice billing.charge [more targets] [--depth 1] [--max-tokens 1500]
    dc-engine outline shop/billing.py
    dc-engine replace billing.charge new_code.py      (or '-' for stdin)
    dc-engine bench billing.charge [more targets]
    dc-engine contract-create spec.json
    dc-engine contract-check <id>
    dc-engine contract-list
    dc-engine hook pre-edit|post-edit|stop     (Claude Code; JSON on stdin)
    dc-engine hook preToolUse|beforeShellExecution|beforeMCPExecution|afterFileEdit|stop --format cursor
    dc-engine install --claude-code
    dc-engine install --cursor
    dc-engine install --uninstall
    dc-engine install --cursor --uninstall
    dc-engine tools [--tools slim|full|contracts] [--json]
    dc-engine clean [--days 7]
"""

from __future__ import annotations

import argparse
import json
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
    m = sub.add_parser("map"); m.add_argument("--prefix", default=""); m.add_argument("--max-tokens", type=int, default=800)
    f = sub.add_parser("find"); f.add_argument("query"); f.add_argument("--limit", type=int, default=15)
    s = sub.add_parser("show"); s.add_argument("name"); s.add_argument("--body", action="store_true")
    r = sub.add_parser("refs"); r.add_argument("name")
    sl = sub.add_parser("slice"); sl.add_argument("targets", nargs="+")
    sl.add_argument("--depth", type=int, default=1); sl.add_argument("--max-tokens", type=int, default=1500)
    sl.add_argument("--no-bodies", action="store_true")
    o = sub.add_parser("outline"); o.add_argument("path")
    rp = sub.add_parser("replace"); rp.add_argument("name"); rp.add_argument("code_file")
    rp.add_argument("--no-check", action="store_true")
    b = sub.add_parser("bench"); b.add_argument("targets", nargs="+")
    b.add_argument("--depth", type=int, default=1); b.add_argument("--max-tokens", type=int, default=1500)
    cc = sub.add_parser("contract-create"); cc.add_argument("json_file")
    ck = sub.add_parser("contract-check"); ck.add_argument("id")
    sub.add_parser("contract-list")
    am = sub.add_parser("contract-amend"); am.add_argument("id"); am.add_argument("json_file")
    cp = sub.add_parser("checkpoints"); cp.add_argument("id")
    rs = sub.add_parser("restore"); rs.add_argument("id"); rs.add_argument("n", type=int)
    hk = sub.add_parser("hook")
    hk.add_argument("event", choices=[
        "pre-edit", "post-edit", "stop",
        "preToolUse", "beforeShellExecution", "beforeMCPExecution", "afterFileEdit",
    ])
    hk.add_argument("--format", choices=["claude", "cursor"], default="claude",
                    dest="hook_format")
    ins = sub.add_parser("install")
    ins.add_argument("--claude-code", action="store_true")
    ins.add_argument("--cursor", action="store_true")
    ins.add_argument("--uninstall", action="store_true")
    ins.add_argument("--tools", choices=("slim", "full", "contracts"), default="slim")
    tl = sub.add_parser("tools", help="dump the MCP tool surface (no repo needed)")
    tl.add_argument("--tools", choices=("slim", "full", "contracts"), default="slim")
    tl.add_argument("--json", action="store_true")
    cln = sub.add_parser("clean")
    cln.add_argument("--days", type=int, default=7)
    a = p.parse_args(argv)

    if a.cmd == "hook":
        from .hooks import run_cli
        return run_cli(a.event, a.root, a.hook_format)
    if a.cmd == "install":
        from . import install as inst
        do_cursor = bool(a.cursor)
        do_claude = bool(a.claude_code) or not do_cursor
        if a.uninstall:
            print(inst.uninstall(a.root, claude_code=do_claude, cursor=do_cursor))
        else:
            print(inst.install(
                a.root, claude_code=do_claude, cursor=do_cursor, tools=a.tools,
            ))
        return
    if a.cmd == "tools":
        from .server import dump_catalog
        from .catalog import format_catalog
        cat = dump_catalog(a.tools)
        if a.json:
            print(json.dumps(cat, indent=2))
        else:
            print(format_catalog(cat))
        return
    if a.cmd == "clean":
        from .checkpoints import clean_stale
        print(clean_stale(a.root, a.days))
        return

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
    elif a.cmd == "contract-create":
        spec = json.load(sys.stdin) if a.json_file == "-" else json.load(open(a.json_file, encoding="utf-8"))
        out = str(e.create_contract(
            spec["task"], spec.get("targets") or [],
            spec.get("must_change") or [], spec.get("must_preserve") or [],
            spec.get("pytest_ids")))
    elif a.cmd == "contract-check":
        out = str(e.check_contract(a.id))
    elif a.cmd == "contract-list":
        out = e.list_contracts()
    elif a.cmd == "contract-amend":
        spec = json.load(sys.stdin) if a.json_file == "-" else json.load(open(a.json_file, encoding="utf-8"))
        out = str(e.amend_contract(
            a.id, spec.get("add_targets") or spec.get("targets"),
            spec.get("add_must_change") or spec.get("must_change"),
            spec.get("add_must_preserve") or spec.get("must_preserve")))
    elif a.cmd == "checkpoints":
        out = e.list_checkpoints(a.id)
    elif a.cmd == "restore":
        out = e.restore_checkpoint(a.id, a.n)
    else:
        out = _bench(e, a.targets, a.depth, a.max_tokens)
    print(out)


if __name__ == "__main__":
    main()
