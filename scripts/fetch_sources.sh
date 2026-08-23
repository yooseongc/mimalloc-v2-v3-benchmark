#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo="https://github.com/microsoft/mimalloc.git"
fetch_one() {
  local label="$1" ref="$2" sha="$3" destination="$4"
  if [[ -e "$destination" ]]; then
    [[ -d "$destination/.git" ]] || { echo "existing path is not a git checkout: $destination" >&2; exit 1; }
    actual="$(git -C "$destination" rev-parse HEAD)"
    [[ "$actual" == "$sha" ]] || { echo "existing commit mismatch: $actual != $sha" >&2; exit 1; }
    git -C "$destination" diff --quiet
    echo "verified existing source: $label ($sha)"
    return
  fi
  git init -q "$destination"
  git -C "$destination" remote add origin "$repo"
  git -C "$destination" fetch --depth=1 origin "$ref"
  git -C "$destination" checkout -q --detach FETCH_HEAD
  actual="$(git -C "$destination" rev-parse HEAD)"
  [[ "$actual" == "$sha" ]] || { echo "commit mismatch: $actual != $sha" >&2; exit 1; }
  git -C "$destination" diff --quiet
}
fetch_one v2.1.2 refs/tags/v2.1.2 43ce4bd7fd34bcc730c1c7471c99995597415488 "$root/extern/mimalloc-v2.1.2"
fetch_one v3.4.3 refs/tags/v3.4.3 152fbf2634aeafca3774df791b0a77683035f076 "$root/extern/mimalloc-v3.4.3"
fetch_one v3.4.5 refs/tags/v3.4.5 acf2fdd329f9dc2a7ffe3f12a133fe7175e39378 "$root/extern/mimalloc-v3.4.5"
fetch_one v3.5.0 refs/tags/v3.5.0 18b08671c9302247bfb682286e6bf3cc1773f801 "$root/extern/mimalloc-v3.5.0"
# dev3 is resolved once and fetched by immutable commit SHA. Measurement never
# follows the moving branch name after this lock point.
fetch_one dev3-622d421f 622d421f647fc41a2dfe90bc45174770129d78b4 622d421f647fc41a2dfe90bc45174770129d78b4 "$root/extern/mimalloc-dev3-622d421f"
