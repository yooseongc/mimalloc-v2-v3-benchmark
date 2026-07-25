#!/usr/bin/env python3
"""Run a pre-frozen experiment matrix; does not alter raw records."""
import argparse, hashlib, json, os, pathlib, random, subprocess, sys, time, uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]

def sha256_file(path):
    digest = hashlib.sha256()
    with open(str(path), "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def allowed_cpu_list():
    """Return the kernel-authoritative cpuset visible to this process."""
    try:
        with open("/proc/self/status", encoding="utf-8") as status:
            for line in status:
                if line.startswith("Cpus_allowed_list:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None

def command_for(item):
    library = pathlib.Path(item["allocator_library_path"]).resolve()
    benchmark = pathlib.Path(item["benchmark_path"]).resolve()
    command = [str(benchmark), "--scenario", item["scenario"], "--operations",
            str(item["operation_count"]), "--threads", str(item["thread_count"]),
            "--size", str(item["size_bytes"])]
    if item.get("size_profile"):
        command.extend(["--size-profile", item["size_profile"]])
    if item.get("batch_size"):
        command.extend(["--batch-size", str(item["batch_size"])])
    if item.get("free_order"):
        command.extend(["--free-order", item["free_order"]])
    if item.get("touch_mode"):
        command.extend(["--touch-mode", item["touch_mode"]])
    if item.get("allocation_api"):
        command.extend(["--allocation-api", item["allocation_api"]])
    if item.get("idle_ms") is not None:
        command.extend(["--idle-ms", str(item["idle_ms"])])
    if item.get("producer_count"):
        command.extend(["--producers", str(item["producer_count"])])
    if item.get("consumer_count"):
        command.extend(["--consumers", str(item["consumer_count"])])
    if item.get("queue_capacity"):
        command.extend(["--queue-capacity", str(item["queue_capacity"])])
    return command

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=pathlib.Path, required=True,
                        help="frozen JSON execution plan; not a YAML matrix")
    parser.add_argument("--execute", action="store_true",
                        help="required to run; omission performs a dry-run")
    parser.add_argument("--max-runs", type=int, default=0,
                        help="maximum pending repetitions to process; 0 means all")
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    except ValueError as error:
        raise SystemExit("refusing: --plan must be a frozen JSON execution plan: %s" % error)
    if plan.get("design_status") != "Frozen":
        raise SystemExit("refusing: design_status must be Frozen")
    raw_dir = ROOT / "results" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    completed = set()
    for path in raw_dir.glob("*.json"):
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
            if prior.get("valid"):
                completed.add((prior.get("block_id"), prior.get("allocator_library_path"), prior.get("repetition")))
        except ValueError:
            pass
    blocks = {}
    for item in plan["runs"]:
        for repetition in range(int(item.get("repetitions", 1))):
            entry = dict(item)
            entry["repetition"] = repetition + 1
            if (entry.get("block_id"), entry.get("allocator_library_path"), entry["repetition"]) not in completed:
                blocks.setdefault((entry["block_id"], entry["repetition"]), []).append(entry)
    # A block contains the two allocator versions of one repetition.  Shuffle
    # blocks and their internal order deterministically, but never separate the
    # pair across a long sequence of unrelated configurations.
    block_keys = sorted(blocks)
    random.Random(plan["randomization_seed"]).shuffle(block_keys)
    entries = []
    for index, key in enumerate(block_keys):
        block = blocks[key]
        random.Random(plan["randomization_seed"] + index + key[1]).shuffle(block)
        entries.extend(block)
    if args.max_runs > 0:
        entries = entries[:args.max_runs]
    for item in entries:
        command = command_for(item)
        env = {"PATH": os.environ["PATH"], "LD_PRELOAD": item["allocator_library_path"]}
        for name, value in item.get("runtime_options", {}).items():
            key = name if name.startswith("MIMALLOC_") else "MIMALLOC_" + name.upper()
            env[key] = str(value)
        record = {**item, "run_id": str(uuid.uuid4()), "timestamp": time.time(),
                  "command": command, "valid": False, "invalid_reason": None}
        actual_cpu_list = allowed_cpu_list()
        record["cpu_list"] = actual_cpu_list
        if not args.execute:
            record["dry_run"] = True
            print(json.dumps(record, sort_keys=True))
            continue
        expected_library_file = pathlib.Path(item["allocator_library_path"])
        expected_benchmark_file = pathlib.Path(item["benchmark_path"])
        if item.get("allocator_library_sha256") and sha256_file(expected_library_file) != item["allocator_library_sha256"]:
            raise SystemExit("refusing: allocator library SHA-256 differs from frozen plan")
        if item.get("benchmark_sha256") and sha256_file(expected_benchmark_file) != item["benchmark_sha256"]:
            raise SystemExit("refusing: benchmark SHA-256 differs from frozen plan")
        if item.get("cpu_list") and actual_cpu_list != item["cpu_list"]:
            raise SystemExit("refusing: container cpuset differs from frozen plan")
        completed = subprocess.run(command, env=env, universal_newlines=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        record.update(exit_code=completed.returncode, stdout=completed.stdout,
                      stderr=completed.stderr)
        try:
            output = json.loads(completed.stdout)
            record.update(output)
            record["valid"] = completed.returncode == 0 and output.get("valid") is True
            required = ("allocator_version", "allocator_library_path", "elapsed_ns",
                        "operation_count", "checksum")
            if record["valid"] and any(key not in output for key in required):
                record["valid"] = False
                record["invalid_reason"] = "benchmark omitted required result fields"
            expected_library = str(pathlib.Path(item["allocator_library_path"]).resolve())
            actual_library = str(pathlib.Path(str(output.get("allocator_library_path", ""))).resolve())
            if record["valid"] and actual_library != expected_library:
                record["valid"] = False
                record["invalid_reason"] = "loaded allocator library differs from frozen plan"
            # mi_version is an integer such as 212 or 343.  The frozen tag is
            # more precise than that API, so validate its documented major here.
            expected_major = str(item["allocator_version"]).lstrip("v").split(".")[0]
            if record["valid"] and not str(output.get("allocator_version")).startswith(expected_major):
                record["valid"] = False
                record["invalid_reason"] = "detected allocator version differs from frozen plan"
            if not record["valid"] and record["invalid_reason"] is None:
                record["invalid_reason"] = "benchmark validation failed"
        except json.JSONDecodeError:
            record["invalid_reason"] = "benchmark did not emit one JSON record"
        target = raw_dir / f"{record['run_id']}.json"
        target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
