#!/usr/bin/env bash
# Proviso v2 evaluation on a Linux machine or WSL2 Ubuntu: one command, resumable.
#   bash research/v2/run_all.sh                      # all four repositories, in order
#   bash research/v2/run_all.sh sqlalchemy pygments  # some of them
# Each repository's results are committed and pushed as soon as it finishes (research/v2/results/<repo>/).
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO_DIR=$(pwd)
export PROVISO_WORK=${PROVISO_WORK:-$HOME/proviso-work/v2}
VENV=${PROVISO_VENV:-$HOME/proviso-work/venv}
mkdir -p "$PROVISO_WORK"
REPOS=("$@"); [ ${#REPOS[@]} -gt 0 ] || REPOS=(sqlglot sympy sqlalchemy pygments datasette)

case "$REPO_DIR" in /mnt/*) echo "WARNING: repository on the Windows drive ($REPO_DIR); clone it inside WSL (~/Proviso)."; sleep 5;; esac
PY=$(command -v python3 || true)
[ -n "$PY" ] || { echo "python3 not found: sudo apt install -y python3 python3-venv python3-dev"; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || { echo "Python 3.12+ needed."; exit 1; }
for t in git gcc; do command -v $t >/dev/null || { echo "$t not found: sudo apt install -y git build-essential"; exit 1; }; done

[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
# shellcheck disable=SC1091
. "$VENV/bin/activate"
if [ ! -f "$VENV/.proviso-v2-deps" ]; then
  echo "== installing dependencies (pinned)"
  pip install -q --upgrade pip
  pip install -q pytest==9.1.1 pytest-testmon==2.2.0 coverage==7.10.7 execnet==2.1.1 greenlet typing-extensions mpmath hypothesis
  pip install -q -r research/v2/requirements-namerts.txt
  touch "$VENV/.proviso-v2-deps"
fi
if [ ! -d "$PROVISO_WORK/NameRTS" ]; then
  git clone -q https://github.com/ZJU-CTAG/NameRTS.git "$PROVISO_WORK/NameRTS"
  git -C "$PROVISO_WORK/NameRTS" checkout -q f1acdae
fi
[ "${1:-}" = "--setup-only" ] && { echo "== set-up done"; exit 0; }
CORES=$(nproc)
export PROVISO_WORKERS=${PROVISO_WORKERS:-$(( CORES > 2 ? CORES - 1 : 1 ))}

push_results() {
  git add "research/v2/results/$1" 2>/dev/null || true
  if git diff --cached --quiet; then return; fi
  git commit -qm "Proviso v2 evaluation: $1 results ($(hostname), $(date +%F))"
  if git pull -q --rebase && git push -q; then echo "== $1: results pushed"
  else tar -czf "$HOME/proviso-v2-results.tar.gz" research/v2/results; echo "== push failed; results in ~/proviso-v2-results.tar.gz"; fi
}

for r in "${REPOS[@]}"; do
  echo "== $r: start ($(date +%T)); $CORES cores, $PROVISO_WORKERS workers; log $PROVISO_WORK/run.log"
  if python research/v2/pipeline.py "$r" all 2>&1 | tee -a "$PROVISO_WORK/run.log"; then
    push_results "$r"
  else
    echo "== $r: FAILED (see the log); continuing with the next repository"; push_results "$r"
  fi
done
python research/v2/pipeline.py report-all | tee "$PROVISO_WORK/report-all.md"
