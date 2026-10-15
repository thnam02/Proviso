"""MCP server exposing the engine to coding agents over stdio.

Run:  dc-engine-mcp --root /path/to/repo
      (or: python -m dc_engine.server --root /path/to/repo)

Works with both the 1.x (FastMCP) and 2.x (MCPServer) Python MCP SDKs.

Default tool surface is slim (5 tools). Pass --tools full for the old catalog.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Callable

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore[no-redef]

from .catalog import (
    CONTRACT_POLICIES,
    TOOL_MODES,
    build_catalog,
    parse_contract_policy,
    parse_tools_mode,
)
from .contracts import (
    CREATE_CONTRACT_DESCRIPTION,
    CREATE_CONTRACT_DESCRIPTION_CONTRACTS,
)
from .engine import Engine
from .views import DEFAULT_REPO_MAP_TOKENS, DEFAULT_SLICE_TOKENS, DEFAULT_START_TOKENS

INSTRUCTIONS = """\
Call dc_start(task) FIRST. Output is the exact current source of shown
symbols; do not re-read those files unless something was omitted.

Then dc_contract(action=create) before any Python edit. Edit with
dc_replace_symbol; its result includes contract status. dc_find looks up
symbols or (mode=references) call sites. dc_get_symbol loads one symbol;
include_body=true for source.

Fix every ✗. Amend or close via dc_contract. Hooks deny Python edits without
an active contract. Do not stop while the score is below 1.0. Names:
pkg.mod.Class.method or a unique suffix; @L<line> picks duplicates.
"""

INSTRUCTIONS_OPTIONAL = """\
dc-engine tools are optional. Call dc_start(task) for repo context and a
contract template if useful. Output is the exact current source of shown
symbols; do not re-read those files unless something was omitted.

dc_contract is available but never required; you may edit Python with your
normal tools. dc_replace_symbol replaces one symbol and reports new
lint/callers plus contract status if a contract is open. dc_find looks up
symbols or (mode=references) call sites. dc_get_symbol loads one symbol;
include_body=true for source.

Names: pkg.mod.Class.method or a unique suffix; @L<line> picks duplicates.
"""

INSTRUCTIONS_CONTRACTS = """\
Call dc_contract(action=create) before any Python edit. Use Read and Grep
for context.

Edit with dc_replace_symbol; its result includes contract status. Fix every
✗. Amend or close via dc_contract. Hooks deny Python edits without an
active contract. Do not stop while the score is below 1.0. Names:
pkg.mod.Class.method or a unique suffix; @L<line> picks duplicates.
"""

_DC_CONTRACT_HEAD = (
    "Create, amend, check, or close a delta contract. "
    "action is create | amend | check | close. "
    "create needs task, targets, must_change (must_preserve optional). "
    "amend, check, and close need contract_id; amend takes add_targets / "
    "add_must_change / add_must_preserve. "
)
DC_CONTRACT_DESCRIPTION = _DC_CONTRACT_HEAD + CREATE_CONTRACT_DESCRIPTION
DC_CONTRACT_DESCRIPTION_CONTRACTS = (
    _DC_CONTRACT_HEAD + CREATE_CONTRACT_DESCRIPTION_CONTRACTS
)


def make_tool_functions(
    engine: Engine | None,
    mode: str = "slim",
) -> list[Callable[..., Any]]:
    """Callables registered on the MCP server. engine may be None for dumps."""
    mode = parse_tools_mode(mode)

    def dc_start(task: str, hint_symbols: list[str] | None = None,
                 max_tokens: int = DEFAULT_START_TOKENS) -> str:
        """First call on a task. One response: repo size, compressed map,
        slices for hint_symbols or best-matching names/docs, a contract
        template, and a complete JSON example. On a small repo, skip
        exploration and read files directly."""
        return engine.start(task, hint_symbols or [], max_tokens)

    def dc_get_symbol(name: str, include_body: bool = False) -> str:
        """One symbol's signature, docstring, what it calls, who calls it, and
        (with include_body=true) its exact source."""
        return engine.get_symbol(name, include_body)

    def dc_replace_symbol(name: str, new_code: str, check: bool = True) -> str:
        """Replace one function/method/class with `new_code` (its complete new
        definition, decorators included; indentation is fixed automatically).
        Rejected without changes if the file would not parse. Reports only
        lint/type errors the edit introduced and callers a signature change
        may break. Result includes contract status."""
        return engine.replace_symbol(name, new_code, check)

    def dc_contract(
        action: str,
        task: str = "",
        targets: list[str] | None = None,
        must_change: list[dict] | None = None,
        must_preserve: list[dict] | None = None,
        pytest_ids: list[str] | None = None,
        contract_id: str = "",
        add_targets: list[str] | None = None,
        add_must_change: list[dict] | None = None,
        add_must_preserve: list[dict] | None = None,
        reason: str = "",
    ) -> str:
        act = (action or "").strip().lower()
        if act == "create":
            if not task:
                return "✗ dc_contract create needs task"
            if not targets:
                return "✗ dc_contract create needs targets"
            if not must_change:
                return "✗ dc_contract create needs must_change"
            return str(engine.create_contract(
                task, targets, must_change, must_preserve, pytest_ids,
            ))
        if act == "amend":
            if not contract_id:
                return "✗ dc_contract amend needs contract_id"
            return str(engine.amend_contract(
                contract_id, add_targets, add_must_change, add_must_preserve,
            ))
        if act == "check":
            if not contract_id:
                return "✗ dc_contract check needs contract_id"
            return str(engine.check_contract(contract_id))
        if act == "close":
            if not contract_id:
                return "✗ dc_contract close needs contract_id"
            return engine.close_contract(contract_id, reason or None)
        return "✗ unknown action; use create|amend|check|close"

    dc_contract.__doc__ = (
        DC_CONTRACT_DESCRIPTION_CONTRACTS if mode == "contracts"
        else DC_CONTRACT_DESCRIPTION
    )

    def dc_find(query: str, mode: str = "symbols", limit: int = 15) -> str:
        """Find symbols by (partial) name, or with mode=references every
        resolved call site of a symbol (plus name-matched unresolved sites)."""
        m = (mode or "symbols").strip().lower()
        if m in ("references", "reference", "refs"):
            return engine.find_references(query, limit)
        return engine.find_symbol(query, limit)

    slim = [dc_start, dc_get_symbol, dc_replace_symbol, dc_contract, dc_find]
    if mode == "slim":
        return slim
    if mode == "contracts":
        return [dc_contract, dc_replace_symbol]

    def dc_repo_map(path_prefix: str = "", max_tokens: int = DEFAULT_REPO_MAP_TOKENS) -> str:
        """Outline of the repo: files with class/function signatures and line
        numbers, compressed to fit max_tokens. Use path_prefix to zoom in."""
        return engine.repo_map(path_prefix, max_tokens)

    def dc_find_symbol(query: str, limit: int = 15) -> str:
        """Find functions, methods and classes by (partial) name. Returns
        qualified names, locations, signatures and one-line docs."""
        return engine.find_symbol(query, limit)

    def dc_get_slice(targets: list[str], depth: int = 1,
                     max_tokens: int = DEFAULT_SLICE_TOKENS,
                     include_bodies: bool = True, include_tests: bool = False,
                     include_test_bodies: bool = False) -> str:
        """Context for changing `targets`: their source, plus signatures of
        their callees and callers up to `depth` hops, class context, and calls
        whose target could not be resolved statically. Bodies are included
        only for the targets unless include_test_bodies=true. include_tests=true
        adds test functions that call the targets (name-matched). Fits max_tokens."""
        return engine.get_slice(
            targets, depth, max_tokens, include_bodies, include_tests,
            include_test_bodies,
        )

    def dc_find_references(name: str, limit: int = 40) -> str:
        """Every resolved call site of a symbol, plus possible call sites
        where the receiver's type is unknown (matched by name)."""
        return engine.find_references(name, limit)

    def dc_file_outline(path: str) -> str:
        """Signatures and line ranges of everything defined in one file."""
        return engine.file_outline(path)

    def dc_insert_symbol(code: str, after: str = "", path: str = "", check: bool = True) -> str:
        """Add new definitions: after=<symbol> inserts right after it at the
        same indentation (e.g. a new method after an existing one);
        path=<file> appends at the end of a file (created if missing)."""
        return engine.insert_symbol(code, after or None, path or None, check)

    def dc_index_status() -> str:
        """Index size, call-graph coverage and which checkers are available."""
        return engine.status()

    def dc_create_contract(task: str, targets: list[str], must_change: list[dict],
                           must_preserve: list[dict] | None = None,
                           pytest_ids: list[str] | None = None) -> str:
        return str(engine.create_contract(task, targets, must_change,
                                          must_preserve, pytest_ids))
    dc_create_contract.__doc__ = CREATE_CONTRACT_DESCRIPTION

    def dc_check_contract(contract_id: str) -> str:
        """Compare baseline vs the working tree for one contract. Compact
        ✓/✗ report and a score (satisfied / scorable). Fix every ✗."""
        return str(engine.check_contract(contract_id))

    def dc_get_contract(contract_id: str) -> str:
        """Show a saved contract: task, targets, probes, status."""
        return engine.get_contract(contract_id)

    def dc_list_contracts() -> str:
        """List saved contracts (id, status, task)."""
        return engine.list_contracts()

    def dc_close_contract(contract_id: str, reason: str = "") -> str:
        """Mark a contract closed. If the score is below 1.0, `reason` is
        required. The contract JSON is kept; only the baseline tree is removed."""
        return engine.close_contract(contract_id, reason or None)

    def dc_amend_contract(contract_id: str, add_targets: list[str] | None = None,
                          add_must_change: list[dict] | None = None,
                          add_must_preserve: list[dict] | None = None) -> str:
        """Add targets or probes to an open contract. New probes are validated
        against the frozen baseline, same as at creation."""
        return str(engine.amend_contract(contract_id, add_targets,
                                         add_must_change, add_must_preserve))

    def dc_list_checkpoints(contract_id: str) -> str:
        """List score checkpoints for a contract (n, score, ref)."""
        return engine.list_checkpoints(contract_id)

    def dc_restore_checkpoint(contract_id: str, n: int) -> str:
        """Roll the working tree back to checkpoint n. Only files that differ
        are overwritten; untracked files the checkpoint doesn't know about
        are left alone."""
        return engine.restore_checkpoint(contract_id, n)

    extra = [
        dc_repo_map, dc_find_symbol, dc_get_slice, dc_find_references,
        dc_file_outline, dc_insert_symbol, dc_index_status, dc_create_contract,
        dc_check_contract, dc_get_contract, dc_list_contracts, dc_close_contract,
        dc_amend_contract, dc_list_checkpoints, dc_restore_checkpoint,
    ]
    return slim + extra


def instructions_for(tools: str = "slim", contract_policy: str = "required") -> str:
    mode = parse_tools_mode(tools)
    policy = parse_contract_policy(contract_policy)
    if mode == "contracts":
        return INSTRUCTIONS_CONTRACTS
    if policy == "optional":
        return INSTRUCTIONS_OPTIONAL
    return INSTRUCTIONS


def dump_catalog(mode: str = "slim", contract_policy: str = "required") -> dict:
    inst = instructions_for(mode, contract_policy)
    return build_catalog(inst, make_tool_functions(None, mode), mode)


def build_server(
    root: str,
    tools: str = "slim",
    contracts: str = "required",
) -> _Server:
    engine = Engine(root)
    engine.ensure_fresh(force=False)
    mode = parse_tools_mode(tools)
    server = _Server(
        name="dc-engine",
        instructions=instructions_for(mode, contracts),
    )
    for fn in make_tool_functions(engine, mode):
        server.tool()(fn)
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dc-engine-mcp", description=__doc__)
    parser.add_argument("--root", default=os.environ.get("DC_ROOT", os.getcwd()),
                        help="repository root (default: $DC_ROOT or the current directory)")
    parser.add_argument(
        "--tools", choices=TOOL_MODES, default="slim",
        help="slim (default, 5 tools), contracts (dc_contract + dc_replace_symbol), "
             "or full (legacy catalog)",
    )
    parser.add_argument(
        "--contracts", choices=CONTRACT_POLICIES, default="required",
        help="required (default) or optional (tools ablation: never require dc_contract)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    build_server(args.root, tools=args.tools, contracts=args.contracts).run()


if __name__ == "__main__":
    main()
