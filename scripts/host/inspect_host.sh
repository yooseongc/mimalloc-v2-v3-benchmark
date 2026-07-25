#!/usr/bin/env bash
set -euo pipefail
lscpu -e
numactl --hardware
cat /proc/sys/kernel/numa_balancing
cat /sys/kernel/mm/transparent_hugepage/enabled

