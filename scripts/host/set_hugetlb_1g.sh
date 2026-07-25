#!/usr/bin/env bash
# Save and optionally reserve 1 x 1GiB HugeTLB page for a dedicated test host.
set -euo pipefail
state_file="${MIMALLOC_HUGETLB_STATE_FILE:-/tmp/mimalloc-hugetlb-1g-state}"
target="/sys/kernel/mm/hugepages/hugepages-1048576kB/nr_hugepages"
[[ -r "$target" ]] || { echo "1GiB HugeTLB control unavailable: $target" >&2; exit 1; }
current="$(cat "$target")"
echo "current 1GiB HugeTLB pages: $current"
[[ "${1:-}" == --apply ]] || { echo "no change without --apply"; exit 0; }
[[ ! -e "$state_file" ]] || { echo "refusing: saved state exists at $state_file" >&2; exit 1; }
printf '%s\n' "$current" >"$state_file"
if (( EUID == 0 )); then writer=(tee); else writer=(sudo tee); fi
if ! echo 1 | "${writer[@]}" "$target" >/dev/null; then
  rm -f "$state_file"
  exit 1
fi
[[ "$(cat "$target")" == 1 ]] || { echo "failed to reserve one 1GiB HugeTLB page" >&2; exit 1; }
echo "reserved 1 x 1GiB HugeTLB page; prior value saved in $state_file"
