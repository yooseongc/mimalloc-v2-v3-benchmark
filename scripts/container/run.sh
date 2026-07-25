#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
engine="${CONTAINER_ENGINE:-docker}"
: "${CPUSET_CPUS:?set CPUSET_CPUS}"
: "${CPUSET_MEMS:?set CPUSET_MEMS}"
"$engine" run --rm --network none --cpuset-cpus="$CPUSET_CPUS" --cpuset-mems="$CPUSET_MEMS" --volume "$root:/work:Z" --workdir /work mimalloc-comparison:local "$@"

