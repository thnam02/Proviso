#!/usr/bin/env bash
# Agent study: does Proviso's blast-radius report help a coding agent?
#   3 arms x 12 sqlglot tasks x 2 reps = 72 Claude Code runs (Sonnet), interleaved:
#     baseline         the agent alone
#     impact-noreport  Proviso test selection, report hidden
#     impact           Proviso test selection + blast-radius report
#   measures: hidden tests passed, existing tests broken, wall time, cost, test commands
# Usage (WSL, from the repository root; ANTHROPIC_API_KEY exported in this shell, never written to a file):
#   bash research/agent/run_study.sh            # resumable: finished runs are skipped
#   PROVISO_AGENT_RERUN=impact-noreport,impact bash research/agent/run_study.sh
#                                               # set those arms' runs aside (archived) and run them again; the other
#                                               # arms' finished runs are kept
# Results (raw, relabelled, interception per run) are copied to research/agent/results/ and pushed.
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO_DIR=$(pwd)
W=${PROVISO_AGENT_WORK:-$HOME/proviso-work/agent}     # must be outside the repository (the harness refuses otherwise)
VENV=${PROVISO_AGENT_VENV:-$HOME/proviso-work/agent-venv}
BUDGET=${PROVISO_AGENT_BUDGET_USD:-1.0}                # cap per run (typical runs cost $0.2-0.5)
REPS=${PROVISO_AGENT_REPS:-2}

[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "ANTHROPIC_API_KEY is not set in this shell (export it; do not save it to a file)."; exit 1; }
command -v claude >/dev/null || { echo "Claude Code CLI not found: npm install -g @anthropic-ai/claude-code"; exit 1; }
command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
  || { echo "Python 3.12+ needed"; exit 1; }

# Claude Code's --bare mode ignores hooks given through --settings, so Proviso would never run. Every arm (baseline
# included, for a fair comparison) therefore runs without --bare, in a clean environment with a fresh HOME per run.
export DC_EVAL_CLAUDE_HOST_AUTH=1

# Pre-flight (free: an invalid key, so nothing reaches the model): does this Claude Code fire hooks from --settings?
PF=$(mktemp -d)
printf '{"hooks":{"UserPromptSubmit":[{"hooks":[{"type":"command","command":"touch %s/fired"}]}]}}' "$PF" > "$PF/settings.json"
(cd "$PF" && env -i PATH="$PATH" HOME="$PF" ANTHROPIC_API_KEY=invalid-preflight-key \
   timeout 60 claude -p "hi" --settings "$PF/settings.json" --output-format stream-json --verbose >/dev/null 2>&1 || true)
if [ ! -f "$PF/fired" ]; then
  echo "Pre-flight failed: Claude Code did not run a hook from --settings. Proviso would be inactive; not starting."
  rm -rf "$PF"; exit 1
fi
rm -rf "$PF"
echo "== pre-flight: hooks fire"

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -e "$REPO_DIR" pytest
fi
PY="$VENV/bin/python"

mkdir -p "$W/tasks"
cp "$REPO_DIR"/research/agent/eval/tasks/*.json "$W/tasks/"

if [ -n "${PROVISO_AGENT_RERUN:-}" ]; then
  TAG="rerun-$(date +%Y%m%d-%H%M)"
  echo "== setting aside the runs of: $PROVISO_AGENT_RERUN (-> $W/runs_archive/$TAG)"
  mkdir -p "$W/runs_archive/$TAG"
  for arm in ${PROVISO_AGENT_RERUN//,/ }; do
    for d in "$W"/runs/*/"$arm"; do
      [ -d "$d" ] || continue
      t=$(basename "$(dirname "$d")"); mkdir -p "$W/runs_archive/$TAG/$t"; mv "$d" "$W/runs_archive/$TAG/$t/"
    done
  done
  if [ -f "$W/results.jsonl" ]; then
    cp "$W/results.jsonl" "$W/runs_archive/$TAG/results.jsonl"
    "$PY" - "$W/results.jsonl" "$PROVISO_AGENT_RERUN" <<'PYEOF'
import json, sys
path, arms = sys.argv[1], set(sys.argv[2].split(","))
rows = [l for l in open(path) if l.strip() and json.loads(l).get("arm") not in arms]
open(path, "w").writelines(rows)
print(f"   kept {len(rows)} result rows of the other arms")
PYEOF
  fi
fi

echo "== building Proviso assets per task ($(date +%T))"
"$PY" "$REPO_DIR/research/agent/build_assets.py" "$W"

echo "== pre-flight: does Proviso narrow the tests on each task? ($(date +%T))"
"$PY" "$REPO_DIR/research/agent/preflight_selection.py" "$W"

echo "== running the study ($(date +%T)); budget cap \$$BUDGET per run"
cd "$W"
"$PY" -m dc_eval run --eval-dir "$W" --arms baseline,impact-noreport,impact --reps "$REPS" --model sonnet \
  --max-budget-usd "$BUDGET" --resume
"$PY" -m dc_eval report --eval-dir "$W"

cd "$REPO_DIR"
mkdir -p research/agent/results
cp "$W/results.jsonl" "$W/report.md" research/agent/results/
"$PY" research/agent/relabel.py research/agent/results/results.jsonl "$W/cache/https_github.com_tobymao_sqlglo" \
  "$W/tasks" || echo "== relabel failed (run it by hand later)"
"$PY" research/agent/inspect_runs.py "$W" || echo "== inspect_runs failed (run it by hand later)"
git add research/agent/results
if ! git diff --cached --quiet; then
  git commit -qm "Agent study results ($(hostname), $(date +%F))"
  if git pull -q --rebase && git push -q; then echo "== results pushed"
  else echo "== results committed locally; push them as your normal user: cd $REPO_DIR && git push"; fi
fi
echo "== done ($(date +%T))"
