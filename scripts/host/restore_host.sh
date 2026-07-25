#!/usr/bin/env bash
set -euo pipefail
state_file="${MIMALLOC_THP_STATE_FILE:-/tmp/mimalloc-thp-state}"
[[ -r "$state_file" ]] || { echo "no saved THP state at $state_file" >&2; exit 2; }
mode="$(cat "$state_file")"
[[ "$mode" == never || "$mode" == madvise || "$mode" == always ]] || { echo "invalid saved THP mode" >&2; exit 2; }
if (( EUID == 0 )); then writer=(tee); else writer=(sudo tee); fi
echo "$mode" | "${writer[@]}" /sys/kernel/mm/transparent_hugepage/enabled >/dev/null
rm -f "$state_file"
echo "restored THP=$mode"
