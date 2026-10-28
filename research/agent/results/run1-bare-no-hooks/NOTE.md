# Run 1 (28-29 Oct 2026): invalid as a test of Proviso

Claude Code was started with `--bare`, which ignores hooks passed through `--settings`. Proviso's hooks never ran:
0 interceptions and 0 reports across the 48 Proviso-arm runs (`interception.json`), although the agents issued 362 test
commands, 358 of them broad ones that Proviso rewrites. All 72 runs are therefore baseline runs. They are kept as a record
of agent behaviour without Proviso (e.g. how many test commands agents issue), not as evidence about Proviso.

Fix: every arm now runs without `--bare` in a clean environment (`DC_EVAL_CLAUDE_HOST_AUTH=1`, API key kept), and
`run_study.sh` checks that hooks fire before any paid run.
