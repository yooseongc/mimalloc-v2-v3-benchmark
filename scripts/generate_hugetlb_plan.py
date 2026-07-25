#!/usr/bin/env python3
"""Freeze the common 1GiB HugeTLB reservation experiment; do not execute here."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sha = "46ac4545b6c8375e08ac4894c71032ca9ec55e6e31b454bfc61275595a957b39"
libs = {"v2.1.2": "03a21de3a984a745c1bfe8ae6a6ad2ee79e4202c3364745ccba541e539c51f06",
        "v3.4.3": "192b3a11694cbb86bbd54b5e2e63ed51942f16ad4a11e55fb0bd8fa2ad38bfb2"}
runs=[]
for version in ("v2.1.2", "v3.4.3"):
    runs.append({
      "experiment_id":"tier3-hugetlb-1g-large-alloc-r18", "block_id":"tier3-hugetlb-1g-large-alloc-r18",
      "allocator_name":"mimalloc", "allocator_version":version, "build_profile":"release",
      "allocator_library_path":f"/work/opt/mimalloc-{version}/release/lib64/libmimalloc.so",
      "allocator_library_sha256":libs[version], "benchmark_path":"/work/build/benchmark-release/benchmark/mimalloc-bench",
      "benchmark_sha256":sha, "scenario":"large_alloc", "thread_count":1, "size_bytes":64,
      "size_profile":"fixed", "batch_size":1, "free_order":"fifo", "touch_mode":"per-page", "idle_ms":0,
      "operation_count":70, "warmup_count":0, "seed":20260725,
      "runtime_options":{"MIMALLOC_RESERVE_HUGE_OS_PAGES":"1"}, "thp_mode":"madvise",
      "cpu_list":"0,2,4,6,8,10,12,14", "repetitions":15})
plan={"schema_version":1,"design_status":"Frozen","randomization_seed":20260725,"runs":runs}
(ROOT / "manifests" / "execution-plan-tier3-hugetlb-r18.json").write_text(json.dumps(plan,indent=2)+"\n")
