#!/usr/bin/env bash
set -euo pipefail
value="${1:-}"
[[ "$value" == 0 || "$value" == 1 ]] || { echo "usage: set_numa_balancing.sh 0|1 --apply" >&2; exit 2; }
[[ "${2:-}" == --apply ]] || { echo "current: $(cat /proc/sys/kernel/numa_balancing); no change without --apply"; exit 0; }
echo "$value" | sudo tee /proc/sys/kernel/numa_balancing >/dev/null

