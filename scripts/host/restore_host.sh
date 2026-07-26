#!/usr/bin/env bash
set -euo pipefail
thp_state="${MIMALLOC_THP_STATE_FILE:-/tmp/mimalloc-thp-state}"
numa_state="${MIMALLOC_NUMA_STATE_FILE:-/tmp/mimalloc-numa-balancing-state}"
if (( EUID == 0 )); then writer=(tee); else writer=(sudo tee); fi
restored=0
failed=0
if [[ -e "$thp_state" ]]; then
  if [[ ! -r "$thp_state" ]]; then
    echo "cannot read saved THP state at $thp_state" >&2
    failed=1
  else
    mode="$(cat "$thp_state")"
    if [[ "$mode" != never && "$mode" != madvise && "$mode" != always ]]; then
      echo "invalid saved THP mode" >&2
      failed=1
    elif echo "$mode" | "${writer[@]}" /sys/kernel/mm/transparent_hugepage/enabled >/dev/null &&
         grep -q "\\[$mode\\]" /sys/kernel/mm/transparent_hugepage/enabled; then
      rm -f "$thp_state"
      echo "restored THP=$mode"
      restored=1
    else
      echo "failed to restore THP=$mode; state retained" >&2
      failed=1
    fi
  fi
fi
if [[ -e "$numa_state" ]]; then
  if [[ ! -r "$numa_state" ]]; then
    echo "cannot read saved NUMA balancing state at $numa_state" >&2
    failed=1
  else
    value="$(cat "$numa_state")"
    if [[ "$value" != 0 && "$value" != 1 ]]; then
      echo "invalid saved NUMA balancing value" >&2
      failed=1
    elif echo "$value" | "${writer[@]}" /proc/sys/kernel/numa_balancing >/dev/null &&
         [[ "$(cat /proc/sys/kernel/numa_balancing)" == "$value" ]]; then
      rm -f "$numa_state"
      echo "restored NUMA balancing=$value"
      restored=1
    else
      echo "failed to restore NUMA balancing=$value; state retained" >&2
      failed=1
    fi
  fi
fi
if (( restored == 0 && failed == 0 )); then
  echo "no saved THP or NUMA balancing state" >&2
  exit 2
fi
exit "$failed"
