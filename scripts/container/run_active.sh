#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CPUSET_CPUS="0,2,4,6,8,10,12,14" CPUSET_MEMS="0" \
  "$root/scripts/container/run.sh" python3 scripts/run_active_benchmark.py "$@"
