#!/usr/bin/env python3
"""Freeze CPU-topology Tier 3 comparisons as separate cpuset domains."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sha = "46ac4545b6c8375e08ac4894c71032ca9ec55e6e31b454bfc61275595a957b39"
libs = {"v2.1.2": "03a21de3a984a745c1bfe8ae6a6ad2ee79e4202c3364745ccba541e539c51f06",
        "v3.4.3": "192b3a11694cbb86bbd54b5e2e63ed51942f16ad4a11e55fb0bd8fa2ad38bfb2"}
plans = {
    "execution-plan-tier3-smt-r14.json": ("tier3-smt-local-fixed-r14", "0-15"),
    "execution-plan-tier3-oversubscription-r15.json": ("tier3-oversubscription-local-fixed-r15", "0,2,4,6,8,10,12,14"),
    "execution-plan-tier3-oversubscription-r16.json": ("tier3-oversubscription-local-fixed-r16", "0,2,4,6,8,10,12,14"),
}
for filename, (block, cpu_list) in plans.items():
    runs = []
    for version in ("v2.1.2", "v3.4.3"):
        runs.append({
            "experiment_id": block, "block_id": block, "allocator_name": "mimalloc",
            "allocator_version": version, "build_profile": "release",
            "allocator_library_path": f"/work/opt/mimalloc-{version}/release/lib64/libmimalloc.so",
            "allocator_library_sha256": libs[version],
            "benchmark_path": "/work/build/benchmark-release/benchmark/mimalloc-bench",
            "benchmark_sha256": ("f82513d6e68199a211472bc226f86cbcd8ed318fc081ddb1aa849fb1c137698f"
                                 if "r16" in filename else sha), "scenario": "local_churn", "thread_count": 16,
            "size_bytes": 64, "size_profile": "fixed", "batch_size": 1, "free_order": "fifo",
            "touch_mode": "first-and-last", "operation_count": 400_000_000, "warmup_count": 0,
            "seed": 20260725, "runtime_options": {}, "thp_mode": "madvise",
            "cpu_list": cpu_list, "repetitions": 15,
        })
    plan = {"schema_version": 1, "design_status": "Frozen", "randomization_seed": 20260725, "runs": runs}
    (ROOT / "manifests" / filename).write_text(json.dumps(plan, indent=2) + "\n")
