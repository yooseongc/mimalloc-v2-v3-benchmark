#!/usr/bin/env bash
set -euo pipefail

policy="${1:-}"
plan="${2:-}"
shift $(( $# >= 2 ? 2 : $# ))
[[ "$policy" == upstream-default || "$policy" == normalized ]] ||
  { echo "usage: run_r22_epoch.sh upstream-default|normalized PLAN [runner arguments] --apply" >&2; exit 2; }
[[ -n "$plan" ]] || { echo "missing frozen plan" >&2; exit 2; }
apply=0
runner_args=()
for argument in "$@"; do
  if [[ "$argument" == --apply ]]; then apply=1; else runner_args+=("$argument"); fi
done
[[ "$apply" == 1 ]] || {
  echo "no host change without --apply"
  python3 scripts/run_tcpio_r22.py --plan "$plan" --policy "$policy" "${runner_args[@]}"
  exit 0
}

restore() {
  status=$?
  trap - EXIT INT TERM
  if [[ -n "${runner_pid:-}" ]] && kill -0 "$runner_pid" 2>/dev/null; then
    kill -TERM "$runner_pid" 2>/dev/null || true
    wait "$runner_pid" 2>/dev/null || true
  fi
  thp_state="${MIMALLOC_THP_STATE_FILE:-/tmp/mimalloc-thp-state}"
  numa_state="${MIMALLOC_NUMA_STATE_FILE:-/tmp/mimalloc-numa-balancing-state}"
  if [[ -e "$thp_state" || -e "$numa_state" ]]; then
    scripts/host/restore_host.sh || status=$?
  fi
  exit "$status"
}
trap restore EXIT INT TERM

if [[ -r /proc/sys/kernel/numa_balancing ]]; then
  scripts/host/set_numa_balancing.sh 0 --apply
else
  echo "NUMA balancing control unavailable; proceeding only if the frozen runner policy permits kernel-unsupported"
fi
if [[ "$policy" == upstream-default ]]; then thp=madvise; else thp=never; fi
scripts/host/set_thp.sh "$thp" --apply
python3 scripts/run_tcpio_r22.py --plan "$plan" --policy "$policy" --execute "${runner_args[@]}" &
runner_pid=$!
wait "$runner_pid"
runner_pid=
