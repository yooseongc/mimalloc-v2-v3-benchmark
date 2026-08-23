#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
active="$(tr -d '\r\n' < "$root/experiments/ACTIVE")"
runner="scripts/run_active_benchmark.py"
if [[ "$active" == "r28-memory-return-v1" ]]; then
  runner="scripts/run_memory_return_r28.py"
fi
CPUSET_CPUS="0,2,4,6,8,10,12,14" CPUSET_MEMS="0" \
  "$root/scripts/container/run.sh" python3 "$runner" "$@"
