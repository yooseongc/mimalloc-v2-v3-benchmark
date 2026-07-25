#!/usr/bin/env python3
"""Freeze the short r19 syscall and large-page diagnostic matrix."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPU_LIST = "0,2,4,6,8,10,12,14"
VERSIONS = ("v2.1.2", "v3.4.3")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_libraries():
    manifest = json.loads((ROOT / "manifests" / "builds.json").read_text(encoding="utf-8"))
    libraries = {}
    for build in manifest["builds"]:
        if build.get("profile") == "release" and build.get("version") in VERSIONS:
            libraries[build["version"]] = {
                "path": "/work/" + build["library_path"],
                "sha256": build["library_sha256"],
            }
    missing = set(VERSIONS) - set(libraries)
    if missing:
        raise SystemExit("missing release library manifest entries: " + ", ".join(sorted(missing)))
    return libraries


def main():
    benchmark_host = ROOT / "build" / "benchmark-release" / "benchmark" / "mimalloc-bench"
    if not benchmark_host.is_file():
        raise SystemExit("build benchmark before freezing r19 diagnostic plan")
    benchmark_path = "/work/build/benchmark-release/benchmark/mimalloc-bench"
    benchmark_sha256 = sha256_file(benchmark_host)
    libraries = release_libraries()
    policies = {
        "upstream-default": {"v2.1.2": {}, "v3.4.3": {}},
        "version-native-large-os-pages": {
            "v2.1.2": {"MIMALLOC_LARGE_OS_PAGES": "1"},
            "v3.4.3": {"MIMALLOC_ALLOW_LARGE_OS_PAGES": "1"},
        },
    }
    runs = []
    for policy, by_version in policies.items():
        block = "r19-" + policy
        for version in VERSIONS:
            runs.append({
                "experiment_id": block,
                "block_id": block,
                "allocator_name": "mimalloc",
                "allocator_version": version,
                "build_profile": "release",
                "allocator_library_path": libraries[version]["path"],
                "allocator_library_sha256": libraries[version]["sha256"],
                "benchmark_path": benchmark_path,
                "benchmark_sha256": benchmark_sha256,
                "scenario": "large_alloc",
                "thread_count": 1,
                "size_bytes": 64,
                "size_profile": "fixed",
                "batch_size": 1,
                "free_order": "fifo",
                "touch_mode": "per-page",
                "idle_ms": 0,
                "hold_ms": 200,
                "operation_count": 70,
                "warmup_count": 0,
                "seed": 20260725,
                "runtime_options": by_version[version],
                "thp_mode": "madvise",
                "cpu_list": CPU_LIST,
                "repetitions": 3,
                "diagnostic_kind": "syscall-and-page-state",
                "policy_label": policy,
            })
    plan = {
        "schema_version": 1,
        "design_status": "Frozen",
        "design_revision": "r19-diagnostic",
        "randomization_seed": 20260725,
        "notes": [
            "Diagnostic-only; do not pool with primary throughput results.",
            "Version-native large-OS-page requests are not a normalized policy comparison.",
        ],
        "runs": runs,
    }
    out = ROOT / "manifests" / "execution-plan-diagnostic-r19.json"
    out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
