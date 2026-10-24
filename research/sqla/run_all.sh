#!/usr/bin/env bash
# One-command run of the SQLAlchemy study (research/sqla/pipeline.py) on a Linux machine or WSL2 (Ubuntu).
#   bash research/sqla/run_all.sh            # everything; safe to re-run, finished stages are skipped
#   bash research/sqla/run_all.sh select     # one stage
# Work files go to $PROVISO_WORK (default ~/proviso-work/sqla); results to research/sqla/results/, which are
# committed and pushed at the end if git can push, else packed into ~/proviso-sqla-results.tar.gz.
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO=$(pwd)
export PROVISO_WORK=${PROVISO_WORK:-$HOME/proviso-work/sqla}
VENV=${PROVISO_VENV:-$HOME/proviso-work/venv}
mkdir -p "$PROVISO_WORK"

case "$REPO" in /mnt/*) echo "WARNING: the repository is on the Windows drive ($REPO). Clone it inside WSL (e.g. ~/Proviso):"
  echo "         runs on /mnt/c are many times slower."; sleep 5;; esac

PY=$(command -v python3 || true)
[ -n "$PY" ] || { echo "python3 not found: sudo apt install -y python3 python3-venv python3-dev"; exit 1; }
"$PY" - <<'EOF' || { echo "Python 3.12 or newer is needed (sys.monitoring)."; exit 1; }
import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)
EOF
for t in git gcc; do command -v $t >/dev/null || { echo "$t not found: sudo apt install -y git build-essential"; exit 1; }; done

if [ ! -x "$VENV/bin/python" ]; then
  echo "== creating virtual environment $VENV"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
. "$VENV/bin/activate"
if [ ! -f "$VENV/.proviso-deps-ok" ]; then
  echo "== installing dependencies (pinned)"
  pip install -q --upgrade pip
  pip install -q pytest==9.1.1 greenlet typing-extensions pytest-testmon==2.2.0 coverage==7.10.7 execnet==2.1.1
  pip install -q -r research/sqla/requirements-namerts.txt
  touch "$VENV/.proviso-deps-ok"
fi
if [ ! -d "$PROVISO_WORK/NameRTS" ]; then
  echo "== fetching NameRTS (replication package, commit f1acdae)"
  git clone -q https://github.com/ZJU-CTAG/NameRTS.git "$PROVISO_WORK/NameRTS"
  git -C "$PROVISO_WORK/NameRTS" checkout -q f1acdae
fi

CORES=$(nproc)
export PROVISO_WORKERS=${PROVISO_WORKERS:-$(( CORES > 2 ? CORES - 1 : 1 ))}
echo "== running on $CORES cores with $PROVISO_WORKERS workers; log: $PROVISO_WORK/run.log"
python research/sqla/pipeline.py "${@:-all}" 2>&1 | tee -a "$PROVISO_WORK/run.log"

echo "== sending results back"
if git add research/sqla/results && git commit -qm "SQLAlchemy study results ($(hostname), $(date +%F))" \
   && git push -q; then
  echo "Results committed and pushed."
else
  tar -czf "$HOME/proviso-sqla-results.tar.gz" research/sqla/results
  echo "Could not push. Results packed in $HOME/proviso-sqla-results.tar.gz (in Windows: \\\\wsl\$\\Ubuntu$HOME)."
fi
