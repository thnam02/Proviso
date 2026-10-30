#!/usr/bin/env bash
# Re-score Proviso's rows on the benchmark with the current dc_engine (after the import-time snapshot fix, FORMAT 11).
# Only Proviso's selection is recomputed (the other selectors do not use the snapshot); no tests are run, no API cost.
#   bash research/v2/run_reproviso.sh            # all five repositories, then the combined report; pushed at the end
set -uo pipefail
cd "$(dirname "$0")/../.."
export PROVISO_WORK=${PROVISO_WORK:-$HOME/proviso-work/v2}
VENV=${PROVISO_VENV:-$HOME/proviso-work/venv}
# shellcheck disable=SC1091
. "$VENV/bin/activate"
for r in sqlglot sympy sqlalchemy pygments datasette; do
  echo "== $r: reproviso ($(date +%T))" | tee -a "$PROVISO_WORK/run.log"
  python research/v2/pipeline.py "$r" reproviso report 2>&1 | tee -a "$PROVISO_WORK/run.log"
done
python research/v2/pipeline.py report-all > research/v2/results/report-all.md
git add research/v2/results
git commit -qm "v2 evaluation: Proviso re-scored after the import-time snapshot fix ($(hostname), $(date +%F))" && \
  git pull -q --rebase && git push -q && echo "== pushed"
echo "== reproviso finished ($(date +%T))"
