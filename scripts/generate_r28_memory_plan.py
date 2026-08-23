#!/usr/bin/env python3
"""Generate the isolated r28 enhanced memory-return plan."""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
R27 = ROOT / "experiments" / "r27-dev3-snapshot-v1" / "plan.json"
DIRECTORY = ROOT / "experiments" / "r28-memory-return-v1"
CONTRACT = DIRECTORY / "contract.md"
OUTPUT = DIRECTORY / "plan.json"
RUNNER = ROOT / "scripts" / "run_memory_return_r28.py"
RUNNER_BASE = ROOT / "scripts" / "run_active_benchmark.py"
BENCHMARK = ROOT / "build" / "benchmark-release" / "benchmark" / "mimalloc-bench"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def block(block_id, mode, policy="upstream-default", runtime_options=None):
    return {
        "block_id": block_id,
        "profile": "memory-return",
        "scenario": "memory_return",
        "thread_count": 1,
        "size_bytes": 65536,
        "size_profile": "fixed",
        "batch_size": 8192,
        "free_order": "fifo",
        "touch_mode": "per-page",
        "operation_count": 1,
        "smoke_operation_count": 1,
        "expected_operation_count": 8192,
        "idle_ms": 5000,
        "memory_return_mode": mode,
        "memory_action_interval_ms": 10,
        "reallocate_after_observe": 1,
        "policy": policy,
        "runtime_options": runtime_options or {},
    }


def main():
    r27 = json.loads(R27.read_text(encoding="utf-8"))
    plan = {
        "schema_version": 3,
        "comparison_id": "r28-memory-return-v1",
        "comparison_versions": list(r27["comparison_versions"]),
        "design_status": "Frozen",
        "design_revision": "r28-memory-return-v1",
        "contract_path": "experiments/r28-memory-return-v1/contract.md",
        "contract_sha256": sha256(CONTRACT),
        "result_namespace": "r28-memory-return-v1",
        "randomization_seed": 20260828,
        "container_image_digest": r27["container_image_digest"],
        "environment": dict(r27["environment"]),
        "benchmark": {"path": r27["benchmark"]["path"], "sha256": sha256(BENCHMARK)},
        "runner": {
            "path": "scripts/run_memory_return_r28.py",
            "sha256": sha256(RUNNER),
            "dependencies": [{
                "path": "scripts/run_active_benchmark.py",
                "sha256": sha256(RUNNER_BASE),
            }],
        },
        "allocators": list(r27["allocators"]),
        "block_defaults": {
            "allocator_name": "mimalloc",
            "allocation_api": "malloc",
            "warmup_count": 0,
            "smoke_warmup_count": 0,
            "seed": 20260828,
            "repetitions": 15,
        },
        "blocks": [
            block("memory-passive-default", "passive"),
            block("memory-passive-purge1000", "passive", "purge-delay-1000",
                  {"MIMALLOC_PURGE_DELAY": "1000"}),
            block("memory-passive-purge0", "passive", "purge-delay-0",
                  {"MIMALLOC_PURGE_DELAY": "0"}),
            block("memory-activity-default", "allocator-activity"),
            block("memory-collect-normal-default", "collect-normal"),
            block("memory-collect-force-default", "collect-force"),
        ],
    }
    OUTPUT.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
