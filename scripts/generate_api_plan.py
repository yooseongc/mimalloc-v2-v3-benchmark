#!/usr/bin/env python3
"""Freeze secondary allocation-API comparisons; primary malloc results stay separate."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sha = "fba987f9e34c7939ca5a789e70769d29e219bce6bddb0433aeb37a4fc7911702"
libs = {"v2.1.2": "03a21de3a984a745c1bfe8ae6a6ad2ee79e4202c3364745ccba541e539c51f06",
        "v3.4.3": "192b3a11694cbb86bbd54b5e2e63ed51942f16ad4a11e55fb0bd8fa2ad38bfb2"}
runs = []
for api in ("cpp-new", "aligned", "realloc"):
    block = f"tier3-api-{api}-local-fixed-r17"
    for version in ("v2.1.2", "v3.4.3"):
        runs.append({
            "experiment_id": block, "block_id": block, "allocator_name": "mimalloc",
            "allocator_version": version, "build_profile": "release",
            "allocator_library_path": f"/work/opt/mimalloc-{version}/release/lib64/libmimalloc.so",
            "allocator_library_sha256": libs[version],
            "benchmark_path": "/work/build/benchmark-release/benchmark/mimalloc-bench",
            "benchmark_sha256": sha, "scenario": "local_churn", "thread_count": 1,
            "size_bytes": 64, "size_profile": "fixed", "batch_size": 1, "free_order": "fifo",
            "touch_mode": "first-and-last", "allocation_api": api, "operation_count": 200_000_000,
            "warmup_count": 0, "seed": 20260725, "runtime_options": {}, "thp_mode": "madvise",
            "cpu_list": "0,2,4,6,8,10,12,14", "repetitions": 15,
        })
plan = {"schema_version": 1, "design_status": "Frozen", "randomization_seed": 20260725, "runs": runs}
(ROOT / "manifests" / "execution-plan-tier3-api-r17.json").write_text(json.dumps(plan, indent=2) + "\n")
