# dc-engine — Phase 1–3

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
| `dc_create_contract(task, targets, must_change, must_preserve)` | Freeze a baseline and declare which behaviours must change or stay the same |
| `dc_check_contract(id)` | Run probes on baseline vs working tree; compact ✓/✗ report and a score |
| `dc_get_contract` / `dc_list_contracts` / `dc_close_contract(id, reason?)` | Inspect or close a contract (`reason` required if score is below 1.0; JSON is kept) |
| `dc_amend_contract(id, add_targets, add_must_change, add_must_preserve)` | Grow a contract when the change is bigger than planned; new probes are checked against the baseline |
| `dc_list_checkpoints` / `dc_restore_checkpoint` | Score-gated snapshots of the working tree; restore only overwrites files that differ |

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
dc-engine --root <repo> contract-create spec.json
dc-engine --root <repo> contract-check <id>
dc-engine --root <repo> contract-list
dc-engine --root <repo> install --claude-code
dc-engine hook pre-edit|post-edit|stop     # Claude Code; JSON on stdin
```

## Tests

```bash
python -m unittest discover -s tests        # phases 1–3; pyright tests skip if it's not installed
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
  contracts.py  delta-contract schema and JSON persistence
  baseline.py   git worktree / copy snapshot of the repo
  probes.py     isolated probe runner, normalisation, pytest compare
  delta.py      create / validate / check / close / amend
  checkpoints.py score-gated hidden git refs (or copied files)
  active.py     one active contract per repo + enforce mode
  hooks.py      Claude Code pre-edit / post-edit / stop
  install.py    merge hooks into .claude/settings.json and .mcp.json
tests/
  test_engine.py, test_contracts.py, test_phase3.py, mcp_smoke.py, fixtures/shop/
```

## Delta contracts

Before an agent edits, it declares a contract: symbols it will change,
probes whose behaviour must change (with the expected new result), and
probes that must stay the same. The engine freezes a baseline (git
worktree of `stash create`, or a copy if the tree is not a git repo),
checks that `expect_old` actually matches current behaviour, and later
diffs baseline vs working tree by running each probe in a subprocess.

Example — `charge(user, 0)` currently returns a `Receipt`; we want it
to raise `ValueError` without changing tax preview:

```bash
cat > /tmp/zero.json << 'EOF'
{
  "task": "charge(user, Decimal(0)) should raise ValueError",
  "targets": ["billing.validate_amount"],
  "must_change": [{
    "id": "zero",
    "setup": "from decimal import Decimal\nfrom shop.models import User\nfrom shop.billing import charge\nuser = User('a', 'AU')\n",
    "call": "charge(user, Decimal(0))",
    "expect_new": {"raises": "ValueError"}
  }],
  "must_preserve": [{
    "id": "preview",
    "setup": "from decimal import Decimal\nfrom shop.api import preview\n",
    "call": "preview(Decimal('10'), 'AU')"
  }]
}
EOF
dc-engine --root tests/fixtures/shop contract-create /tmp/zero.json
# edit validate_amount to reject amount <= 0, then:
dc-engine --root tests/fixtures/shop contract-check charge-user-decimal-0-should-raise-valueerror
```

```
contract charge-user-decimal-0-should-raise-valueerror: 2/2 satisfied  score 1.0
✓ zero raises ValueError (was: Receipt)
✓ preserved: preview
```

A wrong `expect_old` is rejected at creation ("your understanding of the
current behaviour is wrong: got …"). Probes that already match
`expect_new` are rejected too — nothing to change. Flaky probes (two
baseline runs disagree) are reported and dropped from the score.

## Hooks and checkpoints

```bash
dc-engine --root <repo> install --claude-code
```

That merges (never overwrites) three hook entries into `.claude/settings.json`
and the MCP server into `.mcp.json`. `install --uninstall` removes only those
entries. Mode is `.dc-engine/config.json` → `"enforce": "block"` (default),
`"warn"`, or `"off"`.

Creating a contract makes it **active**. Python edits through Edit/Write/MultiEdit,
Bash commands that clearly write `.py` files, or `dc_replace_symbol` are denied
until then. The Stop hook also blocks once if `.py` files changed with no
contract, however they were written. Closing an unsatisfied contract requires a
`reason`; the Stop hook then warns instead of going silent. After each symbol edit the engine
appends a one-line contract status. Every check that *beats* the best score
saves a checkpoint (`refs/dc/<id>/cp-<n>` in git; a file copy otherwise). A
drop prints `dc_restore_checkpoint`. The Stop hook blocks while the score is
below 1.0, with a loop guard so a stuck agent can still exit.

Blocked-then-fixed session:

```
Agent: Edit shop/billing.py
Hook:  deny — No active delta contract. Call dc_create_contract first.

Agent: dc_create_contract(task="charge(user, 0) should raise",
                          targets=["billing.validate_amount"],
                          must_change=[{id: "zero", call: "charge(user, Decimal(0))",
                                        expect_new: {raises: "ValueError"}}])
       ✓ contract created: charge-zero-should-raise   (now active)

Agent: dc_replace_symbol(validate_amount, … still allows 0)
       contract charge-zero-should-raise: 0/1 ✗ not changed: zero still Receipt(…)

Agent: (tries to stop)
Hook:  decision=block
       contract charge-zero-should-raise: 0/1 satisfied  score 0.0
       ✗ not changed: zero  still Receipt(…)

Agent: dc_replace_symbol(validate_amount, reject amount <= 0)
       ✓ replaced shop.billing.validate_amount
       contract charge-zero-should-raise: 1/1 ✓ zero raises ValueError (was: Receipt)

Agent: (stop)  allowed — score 1.0
```

A later bad edit that drops the score prints:

```
⚠ score dropped 1/1 → 0/1 since checkpoint 2 (best). dc_restore_checkpoint to roll back.
```

`dc-engine clean --days 7` removes closed contracts' leftover baseline
worktrees and `refs/dc/*` refs older than N days.

## Security

Probes are **arbitrary Python** the agent supplies (`setup` + `call`).
`dc_create_contract` and `dc_amend_contract` echo that exact code in their
result so a human can read it before anything runs. Run the layer only on
repos and machines where executing agent-written snippets is acceptable, and
keep `dc_create_contract` / `dc_amend_contract` on **manual approval** in
Claude Code permissions (do not auto-allow those two tools).
