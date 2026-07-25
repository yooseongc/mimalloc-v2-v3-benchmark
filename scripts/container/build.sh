#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
engine="${CONTAINER_ENGINE:-docker}"
"$engine" build --file "$root/container/Dockerfile" --tag mimalloc-comparison:local "$root"

