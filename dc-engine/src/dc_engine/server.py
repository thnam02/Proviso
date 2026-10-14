"""MCP server exposing the engine to coding agents over stdio.

Run:  dc-engine-mcp --root /path/to/repo
      (or: python -m dc_engine.server --root /path/to/repo)

Works with both the 1.x (FastMCP) and 2.x (MCPServer) Python MCP SDKs.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore[no-redef]

from .engine import Engine

INSTRUCTIONS = """\
dc-engine gives you the codebase as symbols instead of files. Prefer it over
reading whole files:
1. dc_repo_map once to see the layout (signatures only).
2. dc_find_symbol to locate code by name; dc_get_slice on the symbols you will
   change to get their bodies plus the signatures of everything they call and
   everything that calls them, in one compact response.
3. dc_get_symbol(include_body=true) only for the extra bodies you actually need.
4. Before editing, dc_create_contract: name the symbols you will change, probes
   for behaviours that must change (expect_new, and expect_old if you think you
   know the current result), and probes for behaviours that must stay the same.
   The engine freezes a baseline and rejects a wrong picture of current behaviour.
5. Edit with dc_replace_symbol (full new definition of one function/class) or
   dc_insert_symbol. Each edit is syntax-checked before it is written and
   returns only the lint/type errors it introduced, plus callers a signature
   change may break. Fix what it reports before moving on.
6. After editing, dc_check_contract. Fix any ✗ before finishing. If the score
   drops, dc_restore_checkpoint. When the change is bigger than planned,
   dc_amend_contract. Then dc_close_contract.
Claude Code hooks will deny Python edits without an active contract. Do not
stop while the contract score is below 1.0.
Use your normal edit tool only for code outside functions/classes (imports,
module constants). Symbol names can be full ("pkg.mod.Class.method") or a
unique suffix ("Class.method"); add "@L<line>" to pick between duplicates.
"""


def build_server(root: str) -> _Server:
    engine = Engine(root)
    engine.ensure_fresh(force=False)
    server = _Server(name="dc-engine", instructions=INSTRUCTIONS)

    @server.tool()
    def dc_repo_map(path_prefix: str = "", max_tokens: int = 2000) -> str:
        """Outline of the repo: files with class/function signatures and line
        numbers, compressed to fit max_tokens. Use path_prefix to zoom in."""
        return engine.repo_map(path_prefix, max_tokens)

    @server.tool()
    def dc_find_symbol(query: str, limit: int = 15) -> str:
        """Find functions, methods and classes by (partial) name. Returns
        qualified names, locations, signatures and one-line docs."""
        return engine.find_symbol(query, limit)

    @server.tool()
    def dc_get_symbol(name: str, include_body: bool = False) -> str:
        """One symbol's signature, docstring, what it calls, who calls it, and
        (with include_body=true) its exact source."""
        return engine.get_symbol(name, include_body)

    @server.tool()
    def dc_get_slice(targets: list[str], depth: int = 1, max_tokens: int = 4000,
                     include_bodies: bool = True) -> str:
        """Context for changing `targets`: their source, plus signatures of
        their callees and callers up to `depth` hops, class context, and calls
        whose target could not be resolved statically. Fits max_tokens."""
        return engine.get_slice(targets, depth, max_tokens, include_bodies)

    @server.tool()
    def dc_find_references(name: str, limit: int = 40) -> str:
        """Every resolved call site of a symbol, plus possible call sites
        where the receiver's type is unknown (matched by name)."""
        return engine.find_references(name, limit)

    @server.tool()
    def dc_file_outline(path: str) -> str:
        """Signatures and line ranges of everything defined in one file."""
        return engine.file_outline(path)

    @server.tool()
    def dc_replace_symbol(name: str, new_code: str, check: bool = True) -> str:
        """Replace one function/method/class with `new_code` (its complete new
        definition, decorators included; indentation is fixed automatically).
        Rejected without changes if the file would not parse. Reports only
        lint/type errors the edit introduced and callers a signature change
        may break."""
        return engine.replace_symbol(name, new_code, check)

    @server.tool()
    def dc_insert_symbol(code: str, after: str = "", path: str = "", check: bool = True) -> str:
        """Add new definitions: after=<symbol> inserts right after it at the
        same indentation (e.g. a new method after an existing one);
        path=<file> appends at the end of a file (created if missing)."""
        return engine.insert_symbol(code, after or None, path or None, check)

    @server.tool()
    def dc_index_status() -> str:
        """Index size, call-graph coverage and which checkers are available."""
        return engine.status()

    @server.tool()
    def dc_create_contract(task: str, targets: list[str], must_change: list[dict],
                           must_preserve: list[dict] | None = None,
                           pytest_ids: list[str] | None = None) -> str:
        """Declare a delta contract before editing. `must_change` / `must_preserve`
        are JSON objects: {id, setup?, call, expect_old?, expect_new?} where
        expect is {"returns": "<repr>"} or {"raises": "ValueError"}. must_change
        probes need expect_new. Returns the contract id, or ✗ if a target
        does not resolve or expect_old does not match the baseline."""
        return str(engine.create_contract(task, targets, must_change,
                                          must_preserve, pytest_ids))

    @server.tool()
    def dc_check_contract(contract_id: str) -> str:
        """Compare baseline vs the working tree for one contract. Compact
        ✓/✗ report and a score (satisfied / scorable). Fix every ✗."""
        return str(engine.check_contract(contract_id))

    @server.tool()
    def dc_get_contract(contract_id: str) -> str:
        """Show a saved contract: task, targets, probes, status."""
        return engine.get_contract(contract_id)

    @server.tool()
    def dc_list_contracts() -> str:
        """List saved contracts (id, status, task)."""
        return engine.list_contracts()

    @server.tool()
    def dc_close_contract(contract_id: str) -> str:
        """Drop the frozen baseline for a contract and mark it closed."""
        return engine.close_contract(contract_id)

    @server.tool()
    def dc_amend_contract(contract_id: str, add_targets: list[str] | None = None,
                          add_must_change: list[dict] | None = None,
                          add_must_preserve: list[dict] | None = None) -> str:
        """Add targets or probes to an open contract. New probes are validated
        against the frozen baseline, same as at creation."""
        return str(engine.amend_contract(contract_id, add_targets,
                                         add_must_change, add_must_preserve))

    @server.tool()
    def dc_list_checkpoints(contract_id: str) -> str:
        """List score checkpoints for a contract (n, score, ref)."""
        return engine.list_checkpoints(contract_id)

    @server.tool()
    def dc_restore_checkpoint(contract_id: str, n: int) -> str:
        """Roll the working tree back to checkpoint n. Only files that differ
        are overwritten; untracked files the checkpoint doesn't know about
        are left alone."""
        return engine.restore_checkpoint(contract_id, n)

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dc-engine-mcp", description=__doc__)
    parser.add_argument("--root", default=os.environ.get("DC_ROOT", os.getcwd()),
                        help="repository root (default: $DC_ROOT or the current directory)")
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    build_server(args.root).run()


if __name__ == "__main__":
    main()
