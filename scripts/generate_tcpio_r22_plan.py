#!/usr/bin/env python3
"""Generate immutable r22 smoke/pilot or calibrated final execution plans."""
import argparse
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOCATORS = {
    "v2.1.2": {
        "commit": "43ce4bd7fd34bcc730c1c7471c99995597415488",
        "path": "/work/opt/mimalloc-v2.1.2/release/lib64/libmimalloc.so",
        "host_path": ROOT / "opt/mimalloc-v2.1.2/release/lib64/libmimalloc.so",
    },
    "v3.4.3": {
        "commit": "152fbf2634aeafca3774df791b0a77683035f076",
        "path": "/work/opt/mimalloc-v3.4.3/release/lib64/libmimalloc.so",
        "host_path": ROOT / "opt/mimalloc-v3.4.3/release/lib64/libmimalloc.so",
    },
}
TOPOLOGIES = {
    "isolated": {"tcpio_count": 3, "policy_count": 4, "record_count": 1, "thread_count": 8},
    "service-like": {"tcpio_count": 8, "policy_count": 10, "record_count": 2, "thread_count": 20},
}


def sha256(path):
    digest = hashlib.sha256()
    with open(str(path), "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_options(policy, version):
    if policy == "upstream-default":
        return {}
    common = {
        "PURGE_DELAY": 1000,
        "ARENA_PURGE_MULT": 1,
        "ARENA_EAGER_COMMIT": 0,
        "PURGE_DECOMMITS": 1,
        "USE_NUMA_NODES": 1,
    }
    if version == "v2.1.2":
        common["LARGE_OS_PAGES"] = 0
    else:
        common["ALLOW_LARGE_OS_PAGES"] = 0
        common["ALLOW_THP"] = 0
    return common


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("smoke", "pilot", "final"), required=True)
    parser.add_argument("--calibration", type=pathlib.Path,
                        help="JSON mapping topology/stage-work to operation count; required for final")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--numa-control-policy",
                        choices=("require-off", "disabled-or-kernel-unsupported"),
                        default="require-off")
    parser.add_argument("--isolated-topology", choices=("original", "record-rebalanced"),
                        default="original")
    parser.add_argument("--backpressure-policy", choices=("invalid-over-5pct", "metric-only"),
                        default="invalid-over-5pct")
    parser.add_argument("--clean-host-audit", action="store_true",
                        help="new revision after excluding runs with competing benchmark containers")
    parser.add_argument("--duration-recalibration", action="store_true",
                        help="new revision after final durations missed the frozen minimum")
    args = parser.parse_args()
    if args.phase == "final" and args.calibration is None:
        raise SystemExit("--calibration is required before freezing the final plan")
    calibration = json.loads(args.calibration.read_text(encoding="utf-8")) if args.calibration else {}
    benchmark_host = ROOT / "build/benchmark-release/benchmark/mimalloc-bench"
    benchmark_hash = sha256(benchmark_host)
    topologies = dict(TOPOLOGIES)
    if args.isolated_topology == "record-rebalanced":
        topologies["isolated"] = {
            "tcpio_count": 3, "policy_count": 3, "record_count": 2, "thread_count": 8,
        }
    if args.duration_recalibration:
        plan_prefix = "r22e"
    elif args.clean_host_audit:
        plan_prefix = "r22d"
    elif args.backpressure_policy == "metric-only":
        plan_prefix = "r22c"
    else:
        plan_prefix = "r22b" if args.isolated_topology == "record-rebalanced" else "r22"
    repetitions = {"smoke": 1, "pilot": 3, "final": 15}[args.phase]
    operations_default = {
        "smoke": {
            "isolated": {"allocator": 10000, "service": 2000},
            "service-like": {"allocator": 10000, "service": 2000},
        },
        "pilot": {
            "isolated": {"allocator": 1000000, "service": 250000},
            # Oversubscribed service roles can add a large scheduling floor;
            # begin conservatively and calibrate from measured pilot duration.
            "service-like": {"allocator": 25000, "service": 25000},
        },
    }
    runs = []
    for topology, topology_fields in topologies.items():
        for stage_work in ("allocator", "service"):
            for policy in ("upstream-default", "normalized"):
                key = "{}/{}".format(topology, stage_work)
                operation_count = (int(calibration[key]) if args.phase == "final"
                                   else operations_default[args.phase][topology][stage_work])
                for version, allocator in ALLOCATORS.items():
                    runs.append({
                        "block_id": "{}-{}-{}-{}-{}".format(
                            plan_prefix, args.phase, topology, stage_work, policy),
                        "run_kind": args.phase,
                        "scenario": "tcp_policy_record",
                        "allocator_version": version,
                        "allocator_commit": allocator["commit"],
                        "allocator_library_path": allocator["path"],
                        "allocator_library_sha256": sha256(allocator["host_path"]),
                        "benchmark_path": "/work/build/benchmark-release/benchmark/mimalloc-bench",
                        "benchmark_sha256": benchmark_hash,
                        "cpu_list": ("0,2,4,6,8,10,12,14" if topology == "isolated" else "0-15"),
                        "policy": policy,
                        "host_thp": "madvise" if policy == "upstream-default" else "never",
                        "runtime_options": runtime_options(policy, version),
                        "operation_count": operation_count,
                        "warmup_count": max(1000, operation_count // 100),
                        "repetitions": repetitions,
                        "queue_capacity": 65536,
                        "return_queue_capacity": 8192,
                        "record_queue_capacity": 8192,
                        "record_bank_bytes": 16 * 1024 * 1024,
                        "record_bank_items": 4096,
                        "payload_profile": "tcp-proxy-v1",
                        "stage_work": stage_work,
                        "topology": topology,
                        "seed": 0x22C0FFEE,
                        "latency_sample_rate": 1024,
                        **topology_fields,
                    })
    if args.phase in ("pilot", "final"):
        control_repetitions = 3
        for topology, topology_fields in topologies.items():
            for policy in ("upstream-default", "normalized"):
                key = "{}/allocator".format(topology)
                operation_count = (int(calibration[key]) if args.phase == "final"
                                   else operations_default[args.phase][topology]["allocator"])
                for version, allocator in ALLOCATORS.items():
                    runs.append({
                        "block_id": "{}-{}-{}-queue-only-{}".format(
                            plan_prefix, args.phase, topology, policy),
                        "run_kind": args.phase + "-control",
                        "scenario": "tcp_policy_record_queue_only",
                        "allocator_version": version,
                        "allocator_commit": allocator["commit"],
                        "allocator_library_path": allocator["path"],
                        "allocator_library_sha256": sha256(allocator["host_path"]),
                        "benchmark_path": "/work/build/benchmark-release/benchmark/mimalloc-bench",
                        "benchmark_sha256": benchmark_hash,
                        "cpu_list": ("0,2,4,6,8,10,12,14" if topology == "isolated" else "0-15"),
                        "policy": policy,
                        "host_thp": "madvise" if policy == "upstream-default" else "never",
                        "runtime_options": runtime_options(policy, version),
                        "operation_count": operation_count,
                        "warmup_count": max(1000, operation_count // 100),
                        "repetitions": control_repetitions,
                        "queue_capacity": 65536,
                        "return_queue_capacity": 8192,
                        "record_queue_capacity": 8192,
                        "record_bank_bytes": 16 * 1024 * 1024,
                        "record_bank_items": 4096,
                        "payload_profile": "tcp-proxy-v1",
                        "stage_work": "allocator",
                        "topology": topology,
                        "seed": 0x22C0FFEE,
                        "latency_sample_rate": 1024,
                        **topology_fields,
                    })
    amendment = args.numa_control_policy == "disabled-or-kernel-unsupported"
    rebalanced = args.isolated_topology == "record-rebalanced"
    metric_only = args.backpressure_policy == "metric-only"
    plan = {
        "schema_version": 1,
        "experiment_id": "r22",
        "design_status": "Frozen",
        "design_revision": (
            "tcpio-r22-amendment-v6" if args.duration_recalibration
            else ("tcpio-r22-amendment-v5" if args.clean_host_audit
            else ("tcpio-r22-amendment-v4" if metric_only
            else ("tcpio-r22-amendment-v3" if rebalanced
            else ("tcpio-r22-amendment-v2" if amendment else "tcpio-r22-amendment-v1")
            )
            )
            )
        ),
        "phase": args.phase,
        "randomization_seed": 0x22B10C,
        "single_numa_only": True,
        "required_numa_balancing": args.numa_control_policy,
        "isolated_topology_revision": args.isolated_topology,
        "backpressure_policy": args.backpressure_policy,
        "host_background_audit": (
            "no-competing-mimalloc-containers"
            if (args.clean_host_audit or args.duration_recalibration)
            else "not-revision-gated"
        ),
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("{} runs (expanded repetitions: {})".format(
        len(runs), sum(int(run["repetitions"]) for run in runs)))


if __name__ == "__main__":
    raise SystemExit(main())
