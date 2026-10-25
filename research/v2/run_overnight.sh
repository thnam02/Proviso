#!/usr/bin/env bash
# Overnight run: the remaining repositories, then the repair and baseline stages for every repository.
#   bash research/v2/run_overnight.sh
# Order: sympy, pygments (held out), datasette (held out, an application) -> each pushed when done;
#        then testmon rows recomputed for sqlglot; then TDAD's rows for all five repositories; then report-all.
# Resumable: run it again and finished work is skipped.
set -uo pipefail
cd "$(dirname "$0")/../.."
export PROVISO_WORK=${PROVISO_WORK:-$HOME/proviso-work/v2}
VENV=${PROVISO_VENV:-$HOME/proviso-work/venv}
LOG="$PROVISO_WORK/run.log"
mkdir -p "$PROVISO_WORK"

# shared set-up (venv, pinned deps, NameRTS) is done by run_all.sh; make sure the venv exists first
if [ ! -x "$VENV/bin/python" ] || [ ! -f "$VENV/.proviso-v2-deps" ]; then
  bash research/v2/run_all.sh --setup-only || true
fi
# shellcheck disable=SC1091
. "$VENV/bin/activate"

if [ ! -f "$VENV/.proviso-v2-extra" ]; then
  echo "== installing TDAD's and datasette's dependencies" | tee -a "$LOG"
  # TDAD (NetworkX backend; its code imports the neo4j driver even when unused)
  pip install -q pydantic-settings gitpython neo4j
  # datasette runtime + test dependencies (from its pyproject.toml; pytest-xdist left out: NameRTS brings its own)
  pip install -q "asgiref>=3.2.10" "click>=7.1.1" "click-default-group>=1.2.3" "Jinja2>=2.10.3" "hupper>=1.9" \
    "httpx2>=2.0" "pluggy>=1.0" "uvicorn>=0.29" "aiofiles>=0.4" "PyYAML>=5.3" "mergedeep>=1.1.1" "itsdangerous>=1.1" \
    "sqlite-utils>=4.0" "asyncinject>=0.7" setuptools "pydantic>=2" "opentelemetry-api>=1.37" \
    "pytest-asyncio>=1.2.0" "beautifulsoup4>=4.8.1" "pytest-timeout>=1.4.2" "trustme>=0.7" "cogapp>=3.3.0" \
    "multipart-form-data-conformance==0.1a0" "opentelemetry-sdk>=1.37" || echo "WARNING: some datasette deps failed"
  touch "$VENV/.proviso-v2-extra"
fi
if [ ! -d "$PROVISO_WORK/TDAD" ]; then
  git clone -q https://github.com/pepealonso95/TDAD.git "$PROVISO_WORK/TDAD"
  git -C "$PROVISO_WORK/TDAD" checkout -q 73d1234d3fd02817bc58f1c03b434aca5027ea78
fi
export TDAD_SRC="$PROVISO_WORK/TDAD/tdad/src"

push() {  # push research/v2/results with a message
  git add research/v2/results 2>/dev/null || true
  git diff --cached --quiet && return
  git commit -qm "$1 ($(hostname), $(date +%F))"
  if git pull -q --rebase && git push -q; then echo "== pushed: $1" | tee -a "$LOG"
  else tar -czf "$HOME/proviso-v2-results.tar.gz" research/v2/results; echo "== push failed; results in ~/proviso-v2-results.tar.gz" | tee -a "$LOG"; fi
}

# 1. remaining repositories (each pushed by run_all.sh when it finishes)
bash research/v2/run_all.sh sympy pygments datasette

# 2. testmon rows for sqlglot (its first run recorded testmon wrongly)
echo "== sqlglot: retestmon ($(date +%T))" | tee -a "$LOG"
python research/v2/pipeline.py sqlglot retestmon report 2>&1 | tee -a "$LOG" && push "v2 evaluation: sqlglot testmon rows recomputed"

# 3. TDAD baseline rows for every repository (static: no tests are run)
for r in sqlglot sqlalchemy sympy pygments datasette; do
  if [ -d "research/v2/results/$r" ]; then
    echo "== $r: TDAD rows ($(date +%T))" | tee -a "$LOG"
    python research/v2/pipeline.py "$r" tdad report 2>&1 | tee -a "$LOG" && push "v2 evaluation: $r TDAD baseline rows"
  fi
done

python research/v2/pipeline.py report-all | tee "$PROVISO_WORK/report-all.md"
cp "$PROVISO_WORK/report-all.md" research/v2/results/report-all.md 2>/dev/null && push "v2 evaluation: combined report"
echo "== overnight run finished ($(date +%T))" | tee -a "$LOG"
