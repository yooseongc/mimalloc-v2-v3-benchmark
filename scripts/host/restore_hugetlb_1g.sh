#!/usr/bin/env bash
set -euo pipefail
state_file="${MIMALLOC_HUGETLB_STATE_FILE:-/tmp/mimalloc-hugetlb-1g-state}"
target="/sys/kernel/mm/hugepages/hugepages-1048576kB/nr_hugepages"
[[ -r "$state_file" ]] || { echo "no saved HugeTLB state at $state_file" >&2; exit 2; }
value="$(cat "$state_file")"
[[ "$value" =~ ^[0-9]+$ ]] || { echo "invalid saved HugeTLB value" >&2; exit 2; }
if (( EUID == 0 )); then writer=(tee); else writer=(sudo tee); fi
echo "$value" | "${writer[@]}" "$target" >/dev/null
[[ "$(cat "$target")" == "$value" ]] || { echo "failed to restore HugeTLB count" >&2; exit 1; }
rm -f "$state_file"
echo "restored 1GiB HugeTLB pages=$value"
