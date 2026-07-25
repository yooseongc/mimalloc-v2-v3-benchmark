#!/usr/bin/env python3
"""Write the post-MPMC full Tier-1 frozen plan after pilot calibration."""
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
base = "/work"
libraries = {"v2.1.2": "03a21de3a984a745c1bfe8ae6a6ad2ee79e4202c3364745ccba541e539c51f06", "v3.4.3": "192b3a11694cbb86bbd54b5e2e63ed51942f16ad4a11e55fb0bd8fa2ad38bfb2"}
benchmark_sha = "5e32febad38b09f472b110c2b849bcf4beb76e8e0aaff72a180fcd6ec032b949"
cells = [
  ("local-fixed-t8", "local_churn", 8, 1000000000, "fixed", 1, "fifo", 0, 0, 0),
  ("local-mixed-wide-t1", "local_churn", 1, 200000000, "mixed-wide", 32, "random", 0, 0, 0),
  ("local-mixed-wide-t8", "local_churn", 8, 400000000, "mixed-wide", 32, "random", 0, 0, 0),
  ("remote-fixed-4x4", "remote_free", 8, 100000000, "fixed", 1, "fifo", 4, 4, 65536),
  ("remote-mixed-wide-4x4", "remote_free", 8, 100000000, "mixed-wide", 1, "fifo", 4, 4, 65536),
]
runs = []
for version in ("v2.1.2", "v3.4.3"):
  for name, scenario, threads, operations, profile, batch, order, producers, consumers, capacity in cells:
    item = {"experiment_id": "tier1-full-" + name + "-r6", "block_id": "tier1-full-" + name + "-r6", "allocator_name": "mimalloc", "allocator_version": version,
            "allocator_library_path": base + "/opt/mimalloc-" + version + "/release/lib64/libmimalloc.so", "allocator_library_sha256": libraries[version],
            "benchmark_path": base + "/build/benchmark-release/benchmark/mimalloc-bench", "benchmark_sha256": benchmark_sha,
            "scenario": scenario, "thread_count": threads, "size_bytes": 64, "size_profile": profile, "batch_size": batch, "free_order": order,
            "touch_mode": "first-and-last", "operation_count": operations, "warmup_count": 0, "seed": 20260725, "runtime_options": {}, "thp_mode": "madvise", "repetitions": 15}
    if producers: item.update(producer_count=producers, consumer_count=consumers, queue_capacity=capacity)
    runs.append(item)
out = ROOT / "manifests/execution-plan-full-core-r6.json"
out.write_text(json.dumps({"schema_version": 1, "design_status": "Frozen", "randomization_seed": 20260725, "runs": runs}, indent=2) + "\n")
print(out)
