#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
benchmark="$root/build/benchmark-release/benchmark/mimalloc-bench"
for version in v2.1.2 v3.4.3; do
  library="$root/opt/mimalloc-$version/release/lib64/libmimalloc.so"
  [[ -x "$benchmark" && -f "$library" ]] || { echo "missing benchmark or $library" >&2; exit 1; }
  LD_PRELOAD="$library" "$benchmark" --scenario local_churn --operations 10000 --threads 1 --size 64
done
