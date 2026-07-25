#!/usr/bin/env bash
set -euo pipefail

expected_cpus=""
while (($#)); do
  case "$1" in
    --expect-cpus) expected_cpus="${2:?missing CPU list}"; shift 2 ;;
    *) echo "usage: $0 [--expect-cpus CPU_LIST]" >&2; exit 2 ;;
  esac
done

missing=()
for command in cmake gcc g++ git numactl python3; do command -v "$command" >/dev/null || missing+=("$command"); done
if ((${#missing[@]})); then printf 'missing: %s\n' "${missing[*]}" >&2; exit 1; fi
[[ -r /proc/self/status ]] || { echo "no proc status" >&2; exit 1; }

allowed="$(awk '/^Cpus_allowed_list:/ {print $2}' /proc/self/status)"
[[ -n "$allowed" ]] || { echo "could not read Cpus_allowed_list" >&2; exit 1; }
if [[ -n "$expected_cpus" && "$allowed" != "$expected_cpus" ]]; then
  echo "invalid affinity: expected $expected_cpus, got $allowed" >&2; exit 1
fi

cgroup_path="$(awk -F: '$1==0 {print $3}' /proc/self/cgroup)"
if [[ -n "$cgroup_path" && -r "/sys/fs/cgroup${cgroup_path}/cpuset.cpus.effective" ]]; then
  effective="$(cat "/sys/fs/cgroup${cgroup_path}/cpuset.cpus.effective")"
else
  effective="unavailable"
fi
if [[ -r /sys/fs/cgroup/cpu.stat ]]; then
  cpu_stat="/sys/fs/cgroup/cpu.stat"
elif [[ -r /sys/fs/cgroup/cpu/cpu.stat ]]; then
  cpu_stat="/sys/fs/cgroup/cpu/cpu.stat"
else
  cpu_stat=""
fi
if [[ -n "$cpu_stat" && "$(awk '$1=="nr_throttled" {print $2}' "$cpu_stat")" != "0" ]]; then
  echo "invalid: cgroup has already recorded CPU throttling" >&2; exit 1
fi

thp="unavailable"
[[ -r /sys/kernel/mm/transparent_hugepage/enabled ]] && thp="$(cat /sys/kernel/mm/transparent_hugepage/enabled)"
printf 'environment validation passed: allowed_cpus=%s effective_cpuset=%s thp=%s\n' "$allowed" "$effective" "$thp"
