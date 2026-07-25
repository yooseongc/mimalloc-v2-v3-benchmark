#!/usr/bin/env python3
"""Freeze r20: fixed-worker remote-free comparison with native large-page requests."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ("v2.1.2", "v3.4.3")
CPU_LIST = "0,2,4,6,8,10,12,14"
NATIVE_OPTIONS = {
    "v2.1.2": {"MIMALLOC_LARGE_OS_PAGES": "1"},
    "v3.4.3": {"MIMALLOC_ALLOW_LARGE_OS_PAGES": "1"},
}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def library_info():
    builds = json.loads((ROOT / "manifests" / "builds.json").read_text(encoding="utf-8"))["builds"]
    selected = {build["version"]: build for build in builds
                if build.get("profile") == "release" and build.get("version") in VERSIONS}
    if set(selected) != set(VERSIONS):
        raise SystemExit("release build manifest is incomplete")
    return selected


def main():
    benchmark = ROOT / "build" / "benchmark-release" / "benchmark" / "mimalloc-bench"
    if not benchmark.is_file():
        raise SystemExit("build benchmark before freezing r20")
    builds = library_info()
    runs = []
    for profile in ("fixed-small", "mixed-wide"):
        block = "r20-native-persistent-remote-" + profile
        for version in VERSIONS:
            build = builds[version]
            runs.append({
                "experiment_id": block, "block_id": block,
                "allocator_name": "mimalloc", "allocator_version": version,
                "build_profile": "release",
                "allocator_library_path": "/work/" + build["library_path"],
                "allocator_library_sha256": build["library_sha256"],
                "benchmark_path": "/work/build/benchmark-release/benchmark/mimalloc-bench",
                "benchmark_sha256": sha256_file(benchmark),
                "scenario": "remote_free", "thread_count": 8,
                "producer_count": 4, "consumer_count": 4, "queue_capacity": 65536,
                "size_bytes": 64, "size_profile": "fixed" if profile == "fixed-small" else "mixed-wide",
                "batch_size": 1, "free_order": "fifo", "touch_mode": "first-and-last",
                "operation_count": 100000000, "warmup_count": 0, "seed": 20260725,
                "runtime_options": NATIVE_OPTIONS[version], "thp_mode": "madvise",
                "cpu_list": CPU_LIST, "repetitions": 15,
                "policy_label": "version-native-large-os-pages-request",
                "workload_note": "fixed worker pool; remote frees model task ownership transfer",
            })
    out = ROOT / "manifests" / "execution-plan-native-persistent-r20.json"
    out.write_text(json.dumps({
        "schema_version": 1, "design_status": "Frozen", "design_revision": "r20-native-persistent",
        "randomization_seed": 20260725,
        "notes": [
            "Diagnostic performance comparison; do not pool with normalized-policy primary results.",
            "Version-native large-OS-page variables are not semantically identical.",
        ],
        "runs": runs,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
