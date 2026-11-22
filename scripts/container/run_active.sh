#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
active="$(tr -d '\r\n' < "$root/experiments/ACTIVE")"
if [[ "$active" != "memory-behavior-v1" ]]; then
  echo "Only the new memory-behavior-v1 workflow is active." >&2
  exit 2
fi
exec docker run --rm --pull=never --network none --ulimit core=0 \
  --cpuset-cpus=0,2,4,6 --cpuset-mems=0 \
  --mount "type=bind,source=$root,target=/work" --workdir /work \
  sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877 \
  python3 observation/run.py measured "$@"
