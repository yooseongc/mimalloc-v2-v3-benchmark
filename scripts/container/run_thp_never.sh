#!/usr/bin/env bash
set -euo pipefail
export MIMALLOC_THP_STATE_FILE="${MIMALLOC_THP_STATE_FILE:-/work/results/logs/thp-never.state}"
plan="${MIMALLOC_THP_PLAN:-manifests/execution-plan-tier2-thp-never-r9.json}"
restore() {
  if [[ -e "$MIMALLOC_THP_STATE_FILE" ]]; then
    bash scripts/host/restore_host.sh || true
  fi
}
trap restore EXIT INT TERM
bash scripts/host/set_thp.sh never --apply
python3 scripts/run_experiment.py --plan "$plan" --execute
