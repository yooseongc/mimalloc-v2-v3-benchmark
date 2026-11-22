#!/usr/bin/env python3
"""Generate the isolated r23 v3.4.3/v3.4.5 smoke, pilot, or core plan."""
import argparse
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSIONS = ("v3.4.3", "v3.4.5")
SEED = 20260814
CPU_LIST = "0,2,4,6,8,10,12,14"

CELLS = (
    dict(name="local-fixed-t8", scenario="local_churn", thread_count=8,
         size_bytes=64, size_profile="fixed", batch_size=1, free_order="fifo",
         touch_mode="first-and-last", operation_count=1_000_000_000),
    dict(name="local-mixed-wide-t1", scenario="local_churn", thread_count=1,
         size_bytes=64, size_profile="mixed-wide", batch_size=32, free_order="random",
         touch_mode="first-and-last", operation_count=200_000_000),
    dict(name="local-mixed-wide-t8", scenario="local_churn", thread_count=8,
         size_bytes=64, size_profile="mixed-wide", batch_size=32, free_order="random",
         touch_mode="first-and-last", operation_count=400_000_000),
    dict(name="remote-fixed-4x4", scenario="remote_free", thread_count=8,
         producer_count=4, consumer_count=4, queue_capacity=65536, size_bytes=64,
         size_profile="fixed", batch_size=1, free_order="fifo",
         touch_mode="first-and-last", operation_count=100_000_000),
    dict(name="remote-mixed-wide-4x4", scenario="remote_free", thread_count=8,
         producer_count=4, consumer_count=4, queue_capacity=65536, size_bytes=64,
         size_profile="mixed-wide", batch_size=32, free_order="fifo",
         touch_mode="first-and-last", operation_count=100_000_000),
)

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("smoke", "pilot", "core"), required=True)
    parser.add_argument("--revision", choices=("r23", "r23a"), default="r23")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--freeze-core", action="store_true",
                        help="freeze core only after pilot calibration and design amendment")
    parser.add_argument("--calibration", type=pathlib.Path,
                        help="required pilot calibration record when freezing core")
    args = parser.parse_args()
    benchmark_host = ROOT / "build/benchmark-release/benchmark/mimalloc-bench"
    required = [benchmark_host] + [ROOT / f"opt/mimalloc-{v}/release/lib64/libmimalloc.so" for v in VERSIONS]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing build artifact(s): " + ", ".join(missing))
    repetitions = {"smoke": 1, "pilot": 3, "core": 15}[args.stage]
    frozen = args.stage != "core" or args.freeze_core
    calibrated_counts = {}
    if args.stage == "core" and args.freeze_core:
        if not args.calibration or not args.calibration.is_file():
            raise SystemExit("--freeze-core requires --calibration")
        calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
        if calibration.get("comparison_id") != f"v3.4.3-v3.4.5-{args.revision}" or calibration.get("valid_pilot_records") != 30:
            raise SystemExit("calibration does not describe the complete r23 pilot")
        calibrated_counts = {cell["name"]: cell["core_operation_count"] for cell in calibration["cells"]}
    runs = []
    for cell in CELLS:
        operations = min(cell["operation_count"], 100_000) if args.stage == "smoke" else calibrated_counts.get(cell["name"], cell["operation_count"])
        block_id = f"{args.revision}-{args.stage}-{cell['name']}"
        for version in VERSIONS:
            library_host = ROOT / f"opt/mimalloc-{version}/release/lib64/libmimalloc.so"
            item = {
                "experiment_id": block_id, "block_id": block_id,
                "allocator_name": "mimalloc", "allocator_version": version,
                "allocator_commit": {"v3.4.3": "152fbf2634aeafca3774df791b0a77683035f076",
                                     "v3.4.5": "acf2fdd329f9dc2a7ffe3f12a133fe7175e39378"}[version],
                "allocator_library_path": f"/work/opt/mimalloc-{version}/release/lib64/libmimalloc.so",
                "allocator_library_sha256": sha256(library_host),
                "benchmark_path": "/work/build/benchmark-release/benchmark/mimalloc-bench",
                "benchmark_sha256": sha256(benchmark_host),
                **{k: v for k, v in cell.items() if k != "name"},
                "operation_count": operations, "warmup_count": 0, "seed": SEED,
                "runtime_options": {}, "policy": "upstream-default", "thp_mode": "madvise",
                "repetitions": repetitions, "cpu_list": CPU_LIST,
                "design_revision": f"experiment-design amendment {args.revision} (2026-08-14)",
            }
            runs.append(item)
    plan = {"schema_version": 1, "comparison_id": f"v3.4.3-v3.4.5-{args.revision}",
            "comparison_versions": list(VERSIONS),
            "design_status": "Frozen" if frozen else "Draft",
            "calibration_status": ("complete" if args.stage == "core" and frozen else
                                   "provisional" if args.stage in ("pilot", "core") else "not-applicable"),
            "calibration_record": str(args.calibration) if args.calibration else None,
            "randomization_seed": SEED, "runs": runs}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
