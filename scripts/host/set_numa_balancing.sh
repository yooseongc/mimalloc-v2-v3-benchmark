#!/usr/bin/env bash
set -euo pipefail
value="${1:-}"
state_file="${MIMALLOC_NUMA_STATE_FILE:-/tmp/mimalloc-numa-balancing-state}"
control=/proc/sys/kernel/numa_balancing
[[ "$value" == 0 || "$value" == 1 ]] || { echo "usage: set_numa_balancing.sh 0|1 --apply" >&2; exit 2; }
[[ -r "$control" ]] || { echo "NUMA balancing control is unavailable at $control" >&2; exit 1; }
current="$(cat "$control")"
echo "current NUMA balancing=$current"
[[ "${2:-}" == --apply ]] || { echo "no change without --apply"; exit 0; }
[[ ! -e "$state_file" ]] || { echo "refusing: restore state already exists at $state_file" >&2; exit 1; }
[[ "$current" == 0 || "$current" == 1 ]] || { echo "invalid current NUMA balancing value: $current" >&2; exit 1; }
printf '%s\n' "$current" >"$state_file"
if (( EUID == 0 )); then writer=(tee); else writer=(sudo tee); fi
if ! echo "$value" | "${writer[@]}" "$control" >/dev/null; then
  rm -f "$state_file"
  exit 1
fi
actual="$(cat "$control")"
if [[ "$actual" != "$value" ]]; then
  echo "NUMA balancing read-back mismatch: requested=$value actual=$actual; state retained for restore" >&2
  exit 1
fi
echo "applied NUMA balancing=$value; saved prior value=$current in $state_file"
