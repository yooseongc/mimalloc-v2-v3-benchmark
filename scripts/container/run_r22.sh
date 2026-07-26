#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
engine="${CONTAINER_ENGINE:-docker}"
policy="${1:-}"
topology="${2:-}"
plan="${3:-}"
[[ "$policy" == upstream-default || "$policy" == normalized ]] ||
  { echo "usage: run_r22.sh POLICY isolated|service-like [PLAN] --apply" >&2; exit 2; }
[[ "$topology" == isolated || "$topology" == service-like ]] ||
  { echo "usage: run_r22.sh POLICY isolated|service-like [PLAN] --apply" >&2; exit 2; }
[[ -n "$plan" ]] || { echo "missing frozen plan" >&2; exit 2; }
[[ "${4:-}" == --apply ]] || {
  echo "no privileged host change without --apply"
  exit 0
}
if [[ "$topology" == isolated ]]; then cpus="0,2,4,6,8,10,12,14"; else cpus="0-15"; fi

"$engine" run --rm --network none --privileged \
  --cpuset-cpus="$cpus" --cpuset-mems=0 \
  --volume "$root:/work:Z" --workdir /work mimalloc-comparison:local \
  bash scripts/host/run_r22_epoch.sh "$policy" "$plan" \
  --topology "$topology" --apply
