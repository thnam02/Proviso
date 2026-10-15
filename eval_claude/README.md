# Claude Code runs (cloud workspace)

Agent: Claude Code CLI 2.1.300, model claude-opus-5-5, run from a Claude cloud session.
Task: 98bedf649b (sqlglot Oracle partition + flashback), arms baseline and layer, 3 reps each.
dc-engine: commit c074f3e plus the uncommitted changes of 2026-10-16 (dirty hash c85fbbc08da5).

How it differs from the Cursor runs in ../eval:
- DC_EVAL_CLAUDE_HOST_AUTH=1: no --bare and no API key; each run gets a clean environment
  (fresh HOME, no parent CLAUDE_* variables, no proxy, so the agent's shell has no web access).
- DC_EVAL_OFFLINE=1: no package index; pytest comes from the harness interpreter and the
  task repo is linked into the run venv with a .pth file instead of `pip install -e .`.
- The sqlglot source clone stopped at the task's base commit, so the agent could not read
  the upstream fix from git history.
- The Claude Code stop hook fires (it does not in the Cursor CLI), so the layer is fully enforced.

Each runs/<task>/<arm>/<rep>/ keeps metrics.json, stream.jsonl, grading.log, command.json
and (layer) hooks.log. The repo copies and venvs were not kept.
