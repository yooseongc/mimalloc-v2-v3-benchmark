#!/usr/bin/env python3
"""Generate r24 matched three-version smoke, pilot, and calibrated core plans."""
import argparse, hashlib, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSIONS = ("v2.1.2", "v3.4.3", "v3.5.0")
COMMITS = {
    "v2.1.2": "43ce4bd7fd34bcc730c1c7471c99995597415488",
    "v3.4.3": "152fbf2634aeafca3774df791b0a77683035f076",
    "v3.5.0": "18b08671c9302247bfb682286e6bf3cc1773f801",
}
SEED, CPU_LIST = 20260822, "0,2,4,6,8,10,12,14"
CELLS = (
    dict(name="local-fixed-t8", scenario="local_churn", thread_count=8, size_bytes=64,
         size_profile="fixed", batch_size=1, free_order="fifo", touch_mode="first-and-last", operation_count=1_000_000_000),
    dict(name="local-mixed-wide-t1", scenario="local_churn", thread_count=1, size_bytes=64,
         size_profile="mixed-wide", batch_size=32, free_order="random", touch_mode="first-and-last", operation_count=200_000_000),
    dict(name="local-mixed-wide-t8", scenario="local_churn", thread_count=8, size_bytes=64,
         size_profile="mixed-wide", batch_size=32, free_order="random", touch_mode="first-and-last", operation_count=1_047_000_000),
    dict(name="remote-fixed-4x4", scenario="remote_free", thread_count=8, producer_count=4,
         consumer_count=4, queue_capacity=65536, size_bytes=64, size_profile="fixed",
         batch_size=1, free_order="fifo", touch_mode="first-and-last", operation_count=100_000_000),
    dict(name="remote-mixed-wide-4x4", scenario="remote_free", thread_count=8, producer_count=4,
         consumer_count=4, queue_capacity=65536, size_bytes=64, size_profile="mixed-wide",
         batch_size=32, free_order="fifo", touch_mode="first-and-last", operation_count=100_000_000),
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
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--freeze-core", action="store_true")
    parser.add_argument("--calibration", type=pathlib.Path)
    args = parser.parse_args()
    benchmark = ROOT / "build/benchmark-release/benchmark/mimalloc-bench"
    libraries = {v: ROOT / f"opt/mimalloc-{v}/release/lib64/libmimalloc.so" for v in VERSIONS}
    missing = [str(p) for p in (benchmark, *libraries.values()) if not p.is_file()]
    if missing: raise SystemExit("missing artifact(s): " + ", ".join(missing))
    counts = {}
    if args.stage == "core":
        if not args.freeze_core or not args.calibration:
            raise SystemExit("core requires --freeze-core and --calibration")
        calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
        if calibration.get("comparison_id") != "v2.1.2-v3.4.3-v3.5.0-r24" or calibration.get("valid_pilot_records") != 45:
            raise SystemExit("incomplete or wrong r24 calibration")
        counts = {cell["name"]: cell["core_operation_count"] for cell in calibration["cells"]}
    repetitions = {"smoke": 1, "pilot": 3, "core": 15}[args.stage]
    runs = []
    for cell in CELLS:
        operations = min(cell["operation_count"], 100_000) if args.stage == "smoke" else counts.get(cell["name"], cell["operation_count"])
        block_id = f"r24-{args.stage}-{cell['name']}"
        for version in VERSIONS:
            runs.append({"experiment_id": block_id, "block_id": block_id,
                "allocator_name": "mimalloc", "allocator_version": version,
                "allocator_commit": COMMITS[version],
                "allocator_library_path": f"/work/opt/mimalloc-{version}/release/lib64/libmimalloc.so",
                "allocator_library_sha256": sha256(libraries[version]),
                "benchmark_path": "/work/build/benchmark-release/benchmark/mimalloc-bench",
                "benchmark_sha256": sha256(benchmark),
                **{k: v for k, v in cell.items() if k != "name"}, "operation_count": operations,
                "warmup_count": 0, "seed": SEED, "runtime_options": {}, "policy": "upstream-default",
                "thp_mode": "madvise", "repetitions": repetitions, "cpu_list": CPU_LIST,
                "design_revision": "experiment-design amendment r24 (2026-08-22)"})
    plan = {"schema_version": 1, "comparison_id": "v2.1.2-v3.4.3-v3.5.0-r24",
            "comparison_versions": list(VERSIONS), "design_status": "Frozen",
            "calibration_status": "complete" if args.stage == "core" else "provisional",
            "calibration_record": str(args.calibration) if args.calibration else None,
            "randomization_seed": SEED, "runs": runs}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__": main()
