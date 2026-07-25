#!/usr/bin/env python3
"""Run an immutable short diagnostic plan with optional strace and /proc sampling."""
import argparse
import hashlib
import json
import os
import pathlib
import random
import re
import shutil
import subprocess
import sys
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
SYSCALLS = ("mmap", "munmap", "madvise", "brk")
SYSCALL_LINE = re.compile(r"^\s*[0-9.]+\s+[0-9.]+\s+\d+\s+(\d+)(?:\s+(\d+))?\s+(\S+)\s*$")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(str(path), "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def allowed_cpu_list():
    try:
        with open("/proc/self/status", encoding="utf-8") as status:
            for line in status:
                if line.startswith("Cpus_allowed_list:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def read_keyed_kib(path, wanted):
    values = {}
    try:
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                key, separator, rest = line.partition(":")
                if separator and key in wanted:
                    tokens = rest.split()
                    if tokens and tokens[0].isdigit():
                        values[key] = int(tokens[0]) * 1024
    except OSError:
        return None
    return values


def sample_process(pid):
    smaps = read_keyed_kib("/proc/{}/smaps_rollup".format(pid),
                           {"Rss", "Pss", "Private_Dirty", "AnonHugePages"})
    status = read_keyed_kib("/proc/{}/status".format(pid), {"VmRSS", "VmHWM"})
    if smaps is None and status is None:
        return None
    return {"smaps_rollup": smaps or {}, "status": status or {}}


def merge_maximum(maximum, sample):
    if sample is None:
        return maximum
    for section, values in sample.items():
        target = maximum.setdefault(section, {})
        for key, value in values.items():
            target[key] = max(target.get(key, 0), value)
    return maximum


def read_vmstat():
    result = {}
    try:
        with open("/proc/vmstat", encoding="utf-8") as stream:
            for line in stream:
                key, value = line.split()
                if key.startswith("thp_"):
                    result[key] = int(value)
    except OSError:
        return None
    return result


def subtract_counters(before, after):
    if before is None or after is None:
        return None
    return {key: after.get(key, 0) - value for key, value in before.items() if key in after}


def strace_available():
    executable = shutil.which("strace")
    if not executable:
        return None, "strace not installed"
    probe = subprocess.run([executable, "-f", "-qq", "-c", "-o", "/dev/null", "--", "true"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if probe.returncode != 0:
        return None, "strace preflight failed: " + probe.stderr.strip()
    return executable, None


def parse_strace_summary(path):
    counters = {name: {"calls": 0, "errors": 0} for name in SYSCALLS}
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return {"available": False, "reason": str(error)}
    for line in text.splitlines():
        match = SYSCALL_LINE.match(line)
        if not match:
            continue
        calls, errors, name = match.groups()
        if name in counters:
            counters[name] = {"calls": int(calls), "errors": int(errors or 0)}
    return {"available": True, "counters": counters}


def command_for(item, ready_file):
    command = [item["benchmark_path"], "--scenario", item["scenario"], "--operations", str(item["operation_count"]),
               "--threads", str(item["thread_count"]), "--size", str(item["size_bytes"]),
               "--size-profile", item.get("size_profile", "fixed"), "--batch-size", str(item.get("batch_size", 1)),
               "--free-order", item.get("free_order", "fifo"), "--touch-mode", item.get("touch_mode", "first-and-last"),
               "--idle-ms", str(item.get("idle_ms", 0)), "--hold-ms", str(item.get("hold_ms", 0)),
               "--diagnostic-ready-file", str(ready_file)]
    if item.get("allocation_api"):
        command.extend(["--allocation-api", item["allocation_api"]])
    if item.get("producer_count"):
        command.extend(["--producers", str(item["producer_count"])])
    if item.get("consumer_count"):
        command.extend(["--consumers", str(item["consumer_count"])])
    if item.get("queue_capacity"):
        command.extend(["--queue-capacity", str(item["queue_capacity"])])
    return command


def validate_plan_item(item, actual_cpu):
    library = pathlib.Path(item["allocator_library_path"])
    benchmark = pathlib.Path(item["benchmark_path"])
    if sha256_file(library) != item["allocator_library_sha256"]:
        raise SystemExit("refusing: allocator library SHA-256 differs from frozen plan")
    if sha256_file(benchmark) != item["benchmark_sha256"]:
        raise SystemExit("refusing: benchmark SHA-256 differs from frozen plan")
    if item.get("cpu_list") and item["cpu_list"] != actual_cpu:
        raise SystemExit("refusing: container cpuset differs from frozen plan")


def paired_entries(plan):
    pending = {}
    for item in plan["runs"]:
        for repetition in range(int(item.get("repetitions", 1))):
            entry = dict(item)
            entry["repetition"] = repetition + 1
            pending.setdefault((entry["block_id"], entry["repetition"]), []).append(entry)
    keys = sorted(pending)
    random.Random(plan["randomization_seed"]).shuffle(keys)
    ordered = []
    for index, key in enumerate(keys):
        pair = pending[key]
        random.Random(plan["randomization_seed"] + index + key[1]).shuffle(pair)
        ordered.extend(pair)
    return ordered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--execute", action="store_true", help="required to start measurements")
    parser.add_argument("--sample-interval-ms", type=int, default=50)
    parser.add_argument("--no-strace", action="store_true", help="sample process memory without syscall tracing")
    parser.add_argument("--result-tag", default="r19", help="subdirectory under results/raw and results/logs")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if plan.get("design_status") != "Frozen":
        raise SystemExit("refusing: design_status must be Frozen")
    if not args.execute:
        print(json.dumps({"dry_run": True, "planned_runs": len(paired_entries(plan)), "plan": str(args.plan)}))
        return 0
    actual_cpu = allowed_cpu_list()
    strace, strace_reason = (None, "disabled by --no-strace") if args.no_strace else strace_available()
    raw_dir = ROOT / "results" / "raw" / args.result_tag
    log_dir = ROOT / "results" / "logs" / args.result_tag
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    for item in paired_entries(plan):
        validate_plan_item(item, actual_cpu)
        run_id = str(uuid.uuid4())
        ready_file = log_dir / (run_id + ".pid")
        stdout_file = log_dir / (run_id + ".stdout.log")
        stderr_file = log_dir / (run_id + ".stderr.log")
        strace_file = log_dir / (run_id + ".strace.txt")
        command = command_for(item, ready_file)
        environment = {"PATH": os.environ["PATH"], "LD_PRELOAD": item["allocator_library_path"]}
        for name, value in item.get("runtime_options", {}).items():
            key = name if name.startswith("MIMALLOC_") else "MIMALLOC_" + name.upper()
            environment[key] = str(value)
        launched = ([strace, "-f", "-qq", "-c", "-o", str(strace_file), "--"] + command) if strace else command
        thp_before = read_vmstat()
        process = subprocess.Popen(launched, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True)
        max_process, process_samples = {}, []
        sampled_pid = None
        started = time.monotonic()
        while process.poll() is None:
            if sampled_pid is None and ready_file.exists():
                try:
                    sampled_pid = int(ready_file.read_text(encoding="utf-8").strip())
                except ValueError:
                    pass
            if sampled_pid is not None:
                sample = sample_process(sampled_pid)
                merge_maximum(max_process, sample)
                if sample is not None:
                    process_samples.append({"elapsed_ns": int((time.monotonic() - started) * 1e9), **sample})
            time.sleep(args.sample_interval_ms / 1000.0)
        stdout, stderr = process.communicate()
        if sampled_pid is not None:
            sample = sample_process(sampled_pid)
            merge_maximum(max_process, sample)
            if sample is not None:
                process_samples.append({"elapsed_ns": int((time.monotonic() - started) * 1e9), **sample})
        stdout_file.write_text(stdout, encoding="utf-8")
        stderr_file.write_text(stderr, encoding="utf-8")
        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            output = {}
        valid = process.returncode == 0 and output.get("valid") is True
        reason = None
        expected_library = str(pathlib.Path(item["allocator_library_path"]).resolve())
        actual_library = str(pathlib.Path(str(output.get("allocator_library_path", ""))).resolve())
        if valid and actual_library != expected_library:
            valid, reason = False, "loaded allocator library differs from frozen plan"
        expected_major = item["allocator_version"].lstrip("v").split(".")[0]
        if valid and not str(output.get("allocator_version")).startswith(expected_major):
            valid, reason = False, "detected allocator version differs from frozen plan"
        if not valid and reason is None:
            reason = "benchmark validation failed"
        thp_after = read_vmstat()
        record = dict(item)
        record.update(output)
        record.update({
            "run_id": run_id, "timestamp": time.time(), "valid": valid, "invalid_reason": reason,
            "cpu_list": actual_cpu, "command": command, "exit_code": process.returncode,
            "runtime_options": {key: value for key, value in environment.items() if key.startswith("MIMALLOC_")},
            "stdout_path": str(stdout_file), "stderr_path": str(stderr_file),
            "diagnostic": {
                "strace": parse_strace_summary(strace_file) if strace else {"available": False, "reason": strace_reason},
                "strace_path": str(strace_file) if strace else None,
                "sampled_pid": sampled_pid,
                "maximum_process_memory_bytes": max_process,
                "process_memory_samples": process_samples,
                "thp_vmstat_delta": subtract_counters(thp_before, thp_after),
            },
        })
        (raw_dir / (run_id + ".json")).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if ready_file.exists():
            ready_file.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
