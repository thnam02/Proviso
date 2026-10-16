# Phase 3: prototype

`src/dc_engine/proviso.py`, wired as Claude Code hooks (`dc-engine hook proviso-context|proviso-capture|proviso-verify`)
and as eval arms `proviso`, `replay-only`, `tests-only` (`src/dc_eval/arms.py`).

- Capture (PostToolUse/Bash): Python the agent ran against the repo (`python -c`, heredocs, script files) is re-run in
  isolation right away; that output is what the agent saw.
- Verify (Stop): every recorded script is replayed on the current code and compared with the agent's last observation;
  existing tests the change can affect run from a baseline copy against the current code (overlay directory, so the
  agent's own test edits cannot hide a regression). Reports: hard (a result became an error, or an existing test
  passed before and fails now), soft (a result changed after the agent's last post-edit check). At most 3 items,
  2 blocks per task; soft items never block twice; results seen only before any edit never raise a soft item.
- Context (UserPromptSubmit): instruction line plus outlines of files the report names repeatedly and symbols it names,
  capped at 6,000 characters.

Checks:
- `tests/test_proviso.py`: 17 tests; full suite 250 passing.
- `sim.py`: Phase 0 reproduction through the real hooks on the 98be baseline-rep-3 fix: clean fix silent;
  9 of 10 planted bugs blocked (same miss as Phase 0); about 48 s per verify, mostly the affected test suite.
- `smoke_results.json`: one Haiku run per new arm on f337c70ee4; all hooks fire in headless Claude Code, 0 hook errors.
