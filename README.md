# Proviso

**Safe, fast test feedback for coding agents (Python).** After each edit, Proviso runs only the tests the edit can
affect, including tests that depend on data the package builds at import time (dispatch tables, class attributes).

Across five repositories (469 planted bugs and 181 real commits; ground truth = the tests that actually fail), Proviso
missed a failing test in **3%** of test-breaking changes. pytest-testmon missed in 17–24%, NameRTS in 44–61%, and TDAD
in 95–97%. With selection time included, a typical run drops from 27 s to 3 s on sqlglot and from 8 s to 2 s on
pygments. In 72 Claude Code runs on real sqlglot fixes, Proviso cut the agent's median task time from 124 s to 71 s
with no loss in hidden-test score. Full results: [`research/v2/results/report-all.md`](research/v2/results/report-all.md). Paper:
[`paper/kaggle.md`](paper/kaggle.md).

## How it works

1. **Record once per base commit.** The suite runs under a pytest plugin built on Python 3.12's `sys.monitoring`. For
   each test it records:
   - the functions the test executes;
   - the fixtures it uses and the code they run;
   - code run while its test module imports.

   Each test file runs in a fresh interpreter, so caches cannot hide dependencies. A snapshot fingerprints every value
   the package builds at import time: tables, maps, class attributes.
2. **Select on every run.** From `git diff`, Proviso selects the tests that:
   - executed an edited function;
   - read an import-time value that actually changed (it re-snapshots and compares the values);
   - use a changed class.

   A new source file runs everything, and edited tests always run.
3. **In the agent.** A pre-tool hook rewrites broad test commands (`pytest`, `pytest tests/`) into a Proviso run and
   prints a short report of what the change affected.

## Use it on a repository

Requires Python 3.12+ and pytest.

```bash
pip install -e /path/to/Proviso
cd your-repo
# 1. record the dependency map at the base commit (PKG = package directory, e.g. mypkg or src/mypkg)
python -m dc_engine.record --root . --pkg PKG --out .dc-engine/covmap.json tests
# 2. turn on test selection for the hook
echo '{"impact": true, "python": "'"$(which python)"'"}' > .dc-engine/proviso.json
```

Then add the hook to the agent's settings. For Claude Code (`.claude/settings.json`):

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash",
  "hooks": [{"type": "command", "command": "dc-engine hook proviso-pretool"}]}]}}
```

## Reproduce the evaluation

Everything lives in [`research/v2/`](research/v2). It runs on Linux or WSL2 (8+ cores and 16+ GB recommended). Each
stage is resumable, and results are pushed to `research/v2/results/<repo>/` as each repository finishes.

```bash
bash research/v2/run_all.sh            # venv with pinned dependencies, NameRTS, then all five repositories
bash research/v2/run_overnight.sh      # the same, plus TDAD baseline rows, flaky-test check and the combined report
python research/v2/pipeline.py report-all          # rebuild the combined report from the stored results
python research/v2/namerts_repro.py loguru 20      # check our NameRTS setup against its published results
```

| File | Role |
|---|---|
| `pipeline.py` | Stages per repository: baseline, dependency map, planted bugs, ground truth, selection, real commits, flaky-test check, report |
| `rts.py` | The baseline selectors (name matching, static imports, file/function coverage, testmon) and Proviso's ablations |
| `mutants.py` | Planted-bug generator |
| `namerts_driver.py`, `namerts_repro.py` | NameRTS baseline and its validation against NameRTS's published loguru results |
| `tdad_select.py` | TDAD baseline (unmodified, NetworkX backend) |
| `diagnose.py` | Read-only checks of the testmon baselines |
| `results/` | Raw rows (jsonl), per-repository reports and `report-all.md` |

Repositories and pinned commits are listed in `REPOS` at the top of `pipeline.py`. pygments and datasette are held
out: they were pinned before any run, and Proviso's selection logic was not changed after their results.

## Reproduce the agent study

[`research/agent/`](research/agent) runs Claude Code (Sonnet) on 12 real sqlglot fixes in three arms (baseline,
Proviso selection, selection plus the blast-radius report), 2 repetitions each, about $15 in API cost. See
[`research/agent/README.md`](research/agent/README.md); results, per-run interception counts and the selection
pre-flight are in [`research/agent/results/`](research/agent/results).

```bash
bash research/agent/run_study.sh       # needs ANTHROPIC_API_KEY; run as a user without credentials (the agent has a shell)
```

## Layout

```
src/dc_engine/     the tool: recorder (covplugin.py, record.py), import-time snapshot (importstate.py),
                   selection and agent hook (impact.py, proviso.py, hooks.py); the rest is the symbol index and
                   MCP server the hook builds on
research/v2/       evaluation pipeline, baselines and results
paper/             Kaggle paper, literature review, NameRTS analysis
tests/             unit tests (python -m pytest tests)
```

## Limitations

- Speed depends on coupling. On SQLAlchemy and datasette most changes reach most tests, so Proviso stays safe but
  saves little.
- Remaining blind spots: pure-data classes loaded lazily after import, tests that inspect code structure, and state in
  files or the network.
