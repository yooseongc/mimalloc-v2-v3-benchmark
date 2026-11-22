#!/usr/bin/env bash
set -euo pipefail
mode="${1:-}"
state_file="${MIMALLOC_THP_STATE_FILE:-/tmp/mimalloc-thp-state}"
[[ "$mode" == never || "$mode" == madvise || "$mode" == always ]] || { echo "usage: set_thp.sh never|madvise|always --apply" >&2; exit 2; }
current="$(cat /sys/kernel/mm/transparent_hugepage/enabled)"
echo "current: $current"
[[ "${2:-}" == --apply ]] || { echo "no change without --apply"; exit 0; }
[[ ! -e "$state_file" ]] || { echo "refusing: restore state already exists at $state_file" >&2; exit 1; }
current_mode="$(sed -n 's/.*\[\([^]]*\)\].*/\1/p' <<<"$current")"
printf '%s\n' "$current_mode" >"$state_file"
if (( EUID == 0 )); then
  writer=(tee)
else
  writer=(sudo tee)
fi
if ! echo "$mode" | "${writer[@]}" /sys/kernel/mm/transparent_hugepage/enabled >/dev/null; then
  rm -f "$state_file"
  exit 1
fi
actual="$(sed -n 's/.*\[\([^]]*\)\].*/\1/p' /sys/kernel/mm/transparent_hugepage/enabled)"
if [[ "$actual" != "$mode" ]]; then
  echo "THP read-back mismatch: requested=$mode actual=$actual; state retained for restore" >&2
  exit 1
fi
echo "applied THP=$mode; saved prior THP=$current_mode in $state_file"
