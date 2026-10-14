# dc-engine — Phase 1

Symbol-level context and edits for coding agents, served over MCP.
This is Phase 1 of the **Delta Contracts** layer: it sits between a coding
agent (Claude Code, Cursor, Codex…) and your Python codebase so the agent
reads **signatures and slices instead of whole files**, and edits **by
symbol with instant, diffed checks** instead of string search-and-replace.

```
Coding agent ──MCP──▶ dc-engine ──▶ your repo
                      ├─ indexer   symbols, signatures, imports, call graph (SQLite, incremental)
                      ├─ views     repo map · symbol lookup · references · slices (token-budgeted)
                      └─ edit gate symbol edits · syntax gate · ruff/pyright new-diagnostic diff
                                   · broken-caller check on signature changes
```

## Measured on real repos

Index build: ~250 ms for requests / flask / httpx (37–83 files, 12–18k lines).
Re-index after an edit only re-parses the changed file.

Context needed to change one function — `dc_get_slice` (target body + callee
and caller signatures + class context) vs. reading every file that contains
the target, its callees or its callers:

| Repo | Target | Read files | Slice | Saving |
|---|---|---:|---:|---:|
| requests | `Session.request` | 20,395 | 1,771 | 92% |
| requests | `HTTPAdapter.send` | 9,650 | 1,961 | 80% |
| requests | `utils.get_encoding_from_headers` | 23,873 | 498 | 98% |
| flask | `Flask.make_response` | 16,325 | 1,792 | 90% |
| flask | `Flask.full_dispatch_request` | 16,325 | 715 | 96% |
| flask | `helpers.send_from_directory` | 26,394 | 598 | 98% |
| httpx | `Client.send` | 16,429 | 851 | 95% |
| httpx | `Response.json` | 11,175 | 171 | 99% |
| httpx | `URL.join` | 5,379 | 263 | 96% |

Tokens estimated at ~4 characters per token. This compares context *size*
only; it is not yet an end-to-end measurement of an agent solving tasks
(agents also grep and read partial files). That benchmark is the next step.

Static call resolution (library code, excluding tests/docs/examples): 80–94%
of calls whose target is knowable without type inference (plain names,
`self.method`, `super()`, imports incl. relative, aliased, star and package
re-exports). Calls on variables of unknown type (`response.read()`) stay
unresolved and are shown as such — never guessed.

Edit gate on httpx's 2,000-line `_client.py` / `_models.py`: 2–4 s per edit
with ruff + pyright. A signature change additionally type-checks every file
that may call the symbol (~13 s for `URL.join`, which caught 50 broken call
sites across library and test code).

## Install

```bash
cd dc-engine
pip install -e .                 # needs Python 3.10+ and the `mcp` package
pip install ruff pyright         # optional but recommended: edit checks
```

Without ruff/pyright the edit gate still syntax-checks every edit; it just
reports `skipped` for the missing checker. Set `DC_TYPECHECK=off` to skip
pyright (faster edits, no type checking).

## Use with Claude Code

From your project's root:

```bash
claude mcp add --transport stdio dc-engine -- dc-engine-mcp --root "$(pwd)"
```

Or share it with your team via `.mcp.json` in the project root:

```json
{
  "mcpServers": {
    "dc-engine": {
      "type": "stdio",
      "command": "dc-engine-mcp",
      "args": ["--root", "${CLAUDE_PROJECT_DIR:-.}"]
    }
  }
}
```

The index lives in `<repo>/.dc-engine/` (it adds its own `.gitignore`, so it
never shows up in `git status`). Any other MCP client works the same way: run
`dc-engine-mcp --root <repo>` over stdio.

## Tools

| Tool | What the agent gets |
|---|---|
| `dc_repo_map(path_prefix, max_tokens)` | Files → classes/functions with signatures and line numbers; auto-compresses to fit the budget |
| `dc_find_symbol(query)` | Matching symbols, ranked (exact name first) |
| `dc_get_symbol(name, include_body)` | Signature, docstring, calls, external calls, callers; body only on request |
| `dc_get_slice(targets, depth, max_tokens)` | Everything needed to change `targets`: their source, callee/caller signatures, class context, unresolved calls |
| `dc_find_references(name)` | Resolved call sites + possible ones (unknown receiver, matched by name) |
| `dc_file_outline(path)` | One file's structure |
| `dc_replace_symbol(name, new_code)` | Replace one def/class; re-indents, rejects unparseable results, reports only new diagnostics and broken callers |
| `dc_insert_symbol(code, after \| path)` | Add definitions after a symbol or at the end of a file |
| `dc_index_status()` | Index size, resolution coverage, available checkers |

Names can be full (`pkg.mod.Class.method`) or a unique suffix
(`Class.method`); `name@L42` picks between duplicate definitions such as
property setters.

Example edit result:

```
✓ replaced shop.billing.validate_amount  shop/billing.py L22-25 → L22-25
checks: syntax ok · ruff: 1 new · pyright: 2 new
  ruff L25 F821: Undefined name `msg`
  pyright L25 reportUndefinedVariable: "msg" is not defined
  pyright L30 reportCallIssue: Argument missing for parameter "limit"
⚠ signature changed: def validate_amount(amount: Decimal) -> None  →  def validate_amount(amount: Decimal, limit: Decimal) -> None
  1 caller(s) may need updating:
    shop.billing.charge  shop/billing.py:L30
```

## CLI (for trying it out)

```bash
dc-engine --root <repo> status
dc-engine --root <repo> map --max-tokens 2000
dc-engine --root <repo> slice Session.request --depth 1
dc-engine --root <repo> bench Session.request      # slice vs naive file reads
```

## Tests

```bash
python -m unittest discover -s tests        # 31 tests; pyright tests skip if it's not installed
python tests/mcp_smoke.py tests/fixtures/shop   # starts the MCP server over stdio and calls it
```
(`mcp_smoke.py` edits the repo you point it at; run it on a copy.)

## Known limitations (Phase 1)

- **Python only.** Parsing uses the standard-library `ast` module behind a
  parser interface; TypeScript via tree-sitter is the next language.
- **No type inference in the call graph** yet: calls on parameters/locals
  (`client.send()`) are listed as unresolved. Planned: ask pyright/LSP for
  receiver types to close most of the remaining gap.
- **Context can only be kept out, not evicted.** An MCP server can't remove
  what is already in the agent's context; savings come from compact
  responses.
- Re-indenting new code also shifts the contents of multi-line string
  literals inside it (same as any editor re-indent).
- Edits to module-level code outside functions/classes (imports, constants)
  still go through the agent's normal edit tool.

## Layout

```
src/dc_engine/
  parser.py     ast → symbols, imports, call sites
  store.py      SQLite schema and queries
  indexer.py    incremental indexing + static call resolution
  views.py      repo map, symbol, references, slice (token budgets)
  checks.py     ruff / pyright runners and before/after diagnostic diff
  edit_gate.py  replace/insert by symbol
  engine.py     facade used by server, CLI and tests
  server.py     MCP server (works with mcp 1.x and 2.x)
  cli.py        command line
tests/
  test_engine.py, mcp_smoke.py, fixtures/shop/
```

## Next (Phase 2)

Delta contracts on top of this index: a contract schema (targets,
must_change probes, must_preserve), validation of probes against the
unmodified code, and the old-vs-new behaviour-diff runner.
