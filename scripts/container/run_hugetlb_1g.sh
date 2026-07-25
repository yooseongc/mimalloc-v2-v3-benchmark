#!/usr/bin/env bash
set -euo pipefail
export MIMALLOC_HUGETLB_STATE_FILE="${MIMALLOC_HUGETLB_STATE_FILE:-/work/results/logs/hugetlb-1g.state}"
restored=0
restore() {
  if [[ -e "$MIMALLOC_HUGETLB_STATE_FILE" ]]; then
    bash scripts/host/restore_hugetlb_1g.sh || true
  fi
  restored=1
}
trap restore EXIT INT TERM
bash scripts/host/set_hugetlb_1g.sh --apply
python3 scripts/run_experiment.py --plan manifests/execution-plan-tier3-hugetlb-r18.json --execute
