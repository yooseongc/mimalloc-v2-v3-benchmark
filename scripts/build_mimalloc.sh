#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="${1:?usage: build_mimalloc.sh v2.1.2|v3.4.3|v3.4.5|v3.5.0|v3.5.3|dev3-622d421f [profile]}"
profile="${2:-release}"
case "$version" in v2.1.2|v3.4.3|v3.4.5|v3.5.0|v3.5.3|dev3-622d421f) ;; *) exit 2;; esac
case "$profile" in release|secure|local-dynamic-tls) ;; *)
  echo "unsupported profile: $profile (expected release|secure|local-dynamic-tls)" >&2; exit 2;;
esac
source_dir="$root/extern/mimalloc-$version"
build_dir="$root/build/mimalloc-$version/$profile"
prefix="$root/opt/mimalloc-$version/$profile"
[[ -f "$source_dir/CMakeLists.txt" ]] || { echo "missing $source_dir" >&2; exit 1; }
[[ ! -e "$build_dir/CMakeCache.txt" ]] || { echo "refusing build reuse" >&2; exit 1; }
cmake_args=(-DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" -DCMAKE_C_FLAGS_RELEASE="-O3 -DNDEBUG" -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG")
add_if_supported() {
  local option="$1" value="$2"
  if grep -Eq "(option|set)[[:space:]]*\\([[:space:]]*$option([[:space:]]|\\))" "$source_dir/CMakeLists.txt"; then
    cmake_args+=("-D$option=$value")
  else
    echo "not passing unsupported CMake option: $option" >&2
  fi
}
add_if_supported MI_OVERRIDE ON
add_if_supported MI_BUILD_SHARED ON
add_if_supported MI_BUILD_STATIC OFF
add_if_supported MI_BUILD_OBJECT OFF
add_if_supported MI_BUILD_TESTS OFF
add_if_supported MI_SECURE OFF
add_if_supported MI_TRACK_VALGRIND OFF
add_if_supported MI_TRACK_ASAN OFF
add_if_supported MI_SHOW_ERRORS OFF
case "$profile" in
  secure)
    add_if_supported MI_SECURE ON
    ;;
  local-dynamic-tls)
    add_if_supported MI_LOCAL_DYNAMIC_TLS ON
    ;;
esac
cmake -S "$source_dir" -B "$build_dir" "${cmake_args[@]}"
cmake --build "$build_dir" --parallel
cmake --install "$build_dir"
