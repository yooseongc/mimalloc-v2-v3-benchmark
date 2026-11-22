#!/usr/bin/env python3
"""Generate the single-policy tcpio large-page A/B plan."""
import argparse
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOCATORS = {
    "v2.1.2": {
        "commit": "43ce4bd7fd34bcc730c1c7471c99995597415488",
        "host_path": ROOT / "opt/mimalloc-v2.1.2/release/lib64/libmimalloc.so",
        "path": "/work/opt/mimalloc-v2.1.2/release/lib64/libmimalloc.so",
        "runtime_options": {"ALLOW_LARGE_OS_PAGES": 1},
    },
    "v3.4.3": {
        "commit": "152fbf2634aeafca3774df791b0a77683035f076",
        "host_path": ROOT / "opt/mimalloc-v3.4.3/release/lib64/libmimalloc.so",
        "path": "/work/opt/mimalloc-v3.4.3/release/lib64/libmimalloc.so",
        "runtime_options": {"ALLOW_LARGE_OS_PAGES": 1, "ALLOW_THP": 1},
    },
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("smoke", "final"), required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    benchmark = ROOT / "build/benchmark-release/benchmark/mimalloc-bench"
    operation_count = 200000 if args.phase == "smoke" else 34022222
    repetitions = 1 if args.phase == "smoke" else 15
    runs = []
    for version, allocator in ALLOCATORS.items():
        runs.append({
            "block_id": "r23c-{}-service-like-service-large-page-on".format(args.phase),
            "run_kind": args.phase,
            "scenario": "tcp_policy_record",
            "allocator_version": version,
            "allocator_commit": allocator["commit"],
            "allocator_library_path": allocator["path"],
            "allocator_library_sha256": sha256(allocator["host_path"]),
            "benchmark_path": "/work/build/benchmark-release/benchmark/mimalloc-bench",
            "benchmark_sha256": sha256(benchmark),
            "cpu_list": "0-15",
            "policy": "large-page-on",
            "host_thp": "madvise",
            "hugepage_mode": "native-large-os-page-request",
            "runtime_options": allocator["runtime_options"],
            "operation_count": operation_count,
            "warmup_count": max(1000, operation_count // 100),
            "repetitions": repetitions,
            "queue_capacity": 65536,
            "return_queue_capacity": 8192,
            "record_queue_capacity": 8192,
            "record_bank_bytes": 16 * 1024 * 1024,
            "record_bank_items": 4096,
            "payload_profile": "tcp-proxy-v1",
            "stage_work": "service",
            "topology": "service-like",
            "seed": 0x22C0FFEE,
            "latency_sample_rate": 1024,
            "tcpio_count": 8,
            "policy_count": 10,
            "record_count": 2,
            "thread_count": 20,
            "post_drain_observe_ms": 5000,
            "post_drain_sample_ms": 100,
        })
    plan = {
        "schema_version": 1,
        "experiment_id": "r23",
        "design_status": "Frozen",
        "design_revision": "tcpio-large-page-v3",
        "phase": args.phase,
        "randomization_seed": 0x23B10C,
        "required_numa_balancing": "disabled-or-kernel-unsupported",
        "backpressure_policy": "metric-only",
        "primary_metrics": ["throughput", "post_drain_vm_rss_response"],
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("{} runs (expanded repetitions: {})".format(
        len(runs), sum(run["repetitions"] for run in runs)))


if __name__ == "__main__":
    raise SystemExit(main())
