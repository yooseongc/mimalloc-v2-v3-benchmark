#!/usr/bin/env python3
"""Freeze r21: purge-matched native-request sampled-RSS validation."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ("v2.1.2", "v3.4.3")
OPTIONS = {
    "v2.1.2": {"MIMALLOC_LARGE_OS_PAGES": "1", "MIMALLOC_PURGE_DELAY": "1000"},
    "v3.4.3": {"MIMALLOC_ALLOW_LARGE_OS_PAGES": "1", "MIMALLOC_PURGE_DELAY": "1000"},
}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    benchmark = ROOT / "build" / "benchmark-release" / "benchmark" / "mimalloc-bench"
    if not benchmark.is_file():
        raise SystemExit("build benchmark before freezing r21")
    builds = json.loads((ROOT / "manifests" / "builds.json").read_text(encoding="utf-8"))["builds"]
    release = {build["version"]: build for build in builds
               if build.get("profile") == "release" and build.get("version") in VERSIONS}
    if set(release) != set(VERSIONS):
        raise SystemExit("release build manifest is incomplete")
    runs = []
    for version in VERSIONS:
        build = release[version]
        runs.append({
            "experiment_id": "r21-purge1000-native-remote-mixed-wide",
            "block_id": "r21-purge1000-native-remote-mixed-wide",
            "allocator_name": "mimalloc", "allocator_version": version, "build_profile": "release",
            "allocator_library_path": "/work/" + build["library_path"],
            "allocator_library_sha256": build["library_sha256"],
            "benchmark_path": "/work/build/benchmark-release/benchmark/mimalloc-bench",
            "benchmark_sha256": sha256_file(benchmark),
            "scenario": "remote_free", "thread_count": 8, "producer_count": 4, "consumer_count": 4,
            "queue_capacity": 65536, "size_bytes": 64, "size_profile": "mixed-wide", "batch_size": 1,
            "free_order": "fifo", "touch_mode": "first-and-last", "operation_count": 100000000,
            "warmup_count": 0, "seed": 20260725, "runtime_options": OPTIONS[version],
            "thp_mode": "madvise", "cpu_list": "0,2,4,6,8,10,12,14", "repetitions": 15,
            "policy_label": "native-large-os-pages-plus-purge-delay-1000",
        })
    out = ROOT / "manifests" / "execution-plan-purge-matched-r21.json"
    out.write_text(json.dumps({
        "schema_version": 1, "design_status": "Frozen", "design_revision": "r21-purge-matched-rss",
        "randomization_seed": 20260725,
        "notes": ["RSS/AnonHugePages sampled every 100 ms without strace.",
                  "Version-native large-page requests remain non-normalized; purge delay is matched."],
        "runs": runs,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
