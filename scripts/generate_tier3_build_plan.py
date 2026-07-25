#!/usr/bin/env python3
"""Freeze common secure and local-dynamic-TLS build comparison blocks."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
base = "/work"
benchmark_sha = "46ac4545b6c8375e08ac4894c71032ca9ec55e6e31b454bfc61275595a957b39"
libraries = {
    ("secure", "v2.1.2"): ("libmimalloc-secure.so", "9cfe41c42a966772400736926b77120a3a04014d5a94aeb2084aac969ac2d9fe"),
    ("secure", "v3.4.3"): ("libmimalloc-secure.so", "a018d8d5f9b083de1612fbda3f38bf8ba775671393c25e47522708834e3129b7"),
    ("local-dynamic-tls", "v2.1.2"): ("libmimalloc.so", "fc299f4cdd5ea94ea585bdc2a641b681de6e95b3a81691fbdb815babbf24ebe3"),
    ("local-dynamic-tls", "v3.4.3"): ("libmimalloc.so", "e6291955ef620407407bf7499abae0e8147ec3029b8ad95f28e9bb816c2132c8"),
}
runs = []
for profile, threads, operations in (("secure", 1, 200_000_000), ("local-dynamic-tls", 8, 400_000_000)):
    block = f"tier3-{profile}-local-fixed-r10"
    for version in ("v2.1.2", "v3.4.3"):
        libname, digest = libraries[(profile, version)]
        runs.append({
            "experiment_id": block, "block_id": block, "allocator_name": "mimalloc",
            "allocator_version": version, "build_profile": profile,
            "allocator_library_path": f"{base}/opt/mimalloc-{version}/{profile}/lib64/{libname}",
            "allocator_library_sha256": digest,
            "benchmark_path": f"{base}/build/benchmark-release/benchmark/mimalloc-bench",
            "benchmark_sha256": benchmark_sha, "scenario": "local_churn", "thread_count": threads,
            "size_bytes": 64, "size_profile": "fixed", "batch_size": 1, "free_order": "fifo",
            "touch_mode": "first-and-last", "operation_count": operations, "warmup_count": 0,
            "seed": 20260725, "runtime_options": {}, "thp_mode": "madvise", "repetitions": 15,
        })
plan = {"schema_version": 1, "design_status": "Frozen", "randomization_seed": 20260725, "runs": runs}
(ROOT / "manifests" / "execution-plan-tier3-build-r10.json").write_text(json.dumps(plan, indent=2) + "\n")
