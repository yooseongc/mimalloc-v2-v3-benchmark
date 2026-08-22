#!/usr/bin/env python3
"""Execute one r22 host-state epoch.

Raw records are append-only.  The script never changes host state itself; use
scripts/host/run_r22_epoch.sh so THP and NUMA balancing are restored by a trap.
The frozen plan may explicitly permit a kernel with NUMA balancing compiled out.
"""
import argparse
import hashlib
import json
import os
import pathlib
import random
import subprocess
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]


def monotonic_ns():
    return int(time.monotonic() * 1e9)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(str(path), "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def allowed_cpu_list():
    status = read_text("/proc/self/status")
    if status:
        for line in status.splitlines():
            if line.startswith("Cpus_allowed_list:"):
                return line.split(":", 1)[1].strip()
    return None


def expand_cpu_list(specification):
    result = []
    for part in (specification or "").split(","):
        if not part:
            continue
        bounds = part.split("-", 1)
        result.extend(range(int(bounds[0]), int(bounds[-1]) + 1))
    return result


def thp_mode():
    value = read_text("/sys/kernel/mm/transparent_hugepage/enabled")
    if value:
        for token in value.split():
            if token.startswith("[") and token.endswith("]"):
                return token[1:-1]
    return None


def single_numa_node():
    online = read_text("/sys/devices/system/node/online")
    if online is None:
        return False, None
    nodes = expand_cpu_list(online)
    return len(nodes) == 1, online


def keyed_kib(path, wanted):
    values = {}
    text = read_text(path)
    if text is None:
        return None
    for line in text.splitlines():
        key, separator, rest = line.partition(":")
        fields = rest.split()
        if separator and key in wanted and fields and fields[0].isdigit():
            values[key] = int(fields[0]) * 1024
    return values


def sample_process(pid, started):
    status = keyed_kib("/proc/{}/status".format(pid), {"VmRSS", "VmHWM"})
    smaps = keyed_kib("/proc/{}/smaps_rollup".format(pid), {"Rss", "Pss", "AnonHugePages"})
    if status is None and smaps is None:
        return None
    return {
        "elapsed_ns": monotonic_ns() - started,
        "rss_bytes": (status or {}).get("VmRSS"),
        "vmhwm_bytes": (status or {}).get("VmHWM"),
        "pss_bytes": (smaps or {}).get("Pss"),
        "anon_huge_pages_bytes": (smaps or {}).get("AnonHugePages"),
    }


def cgroup_directories(pid):
    text = read_text("/proc/{}/cgroup".format(pid))
    if text is None:
        return None
    for line in text.splitlines():
        hierarchy, controllers, relative = line.split(":", 2)
        if hierarchy == "0" and controllers == "":
            directory = pathlib.Path("/sys/fs/cgroup") / relative.lstrip("/")
            return {"memory": directory, "cpu": directory, "version": 2}
    result = {"memory": None, "cpu": None, "version": 1}
    for line in text.splitlines():
        _, controllers, relative = line.split(":", 2)
        controller_set = set(controllers.split(","))
        if "memory" in controller_set:
            result["memory"] = pathlib.Path("/sys/fs/cgroup/memory") / relative.lstrip("/")
        if controller_set.intersection({"cpu", "cpuacct"}):
            result["cpu"] = pathlib.Path("/sys/fs/cgroup/cpu,cpuacct") / relative.lstrip("/")
    return result


def cgroup_memory_peak(directory):
    if directory is None:
        return None
    value = read_text(directory / "memory.peak")
    if value is None:
        value = read_text(directory / "memory.max_usage_in_bytes")
    return int(value) if value and value.isdigit() else None


def read_flat_counters(path):
    text = read_text(path)
    if text is None:
        return None
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].isdigit():
            result[fields[0]] = int(fields[1])
    return result


def cgroup_snapshot(directories):
    if directories is None:
        return None
    memory = directories.get("memory")
    cpu = directories.get("cpu")
    swap = read_text(memory / "memory.swap.current") if memory else None
    current = read_text(memory / "memory.current") if memory else None
    if current is None and memory:
        current = read_text(memory / "memory.usage_in_bytes")
    return {
        "version": directories.get("version"),
        "cpu_stat": read_flat_counters(cpu / "cpu.stat") if cpu else None,
        "memory_events": read_flat_counters(memory / "memory.events") if memory else None,
        "memory_current": int(current) if current and current.isdigit() else None,
        "memory_swap_current": int(swap) if swap and swap.isdigit() else None,
        "memory_peak": cgroup_memory_peak(memory),
    }


def command_for(item, ready_file):
    command = [
        item["benchmark_path"], "--scenario", item.get("scenario", "tcp_policy_record"),
        "--operations", str(item["operation_count"]),
        "--threads", str(item["thread_count"]),
        "--size", "64",
        "--tcpio", str(item["tcpio_count"]),
        "--policy", str(item["policy_count"]),
        "--record", str(item["record_count"]),
        "--queue-capacity", str(item["queue_capacity"]),
        "--return-queue-capacity", str(item["return_queue_capacity"]),
        "--record-queue-capacity", str(item.get("record_queue_capacity", 8192)),
        "--record-bank-bytes", str(item["record_bank_bytes"]),
        "--record-bank-items", str(item["record_bank_items"]),
        "--payload-profile", item["payload_profile"],
        "--stage-work", item["stage_work"],
        "--topology", item["topology"],
        "--warmup-count", str(item["warmup_count"]),
        "--seed", str(item["seed"]),
        "--latency-sample-rate", str(item["latency_sample_rate"]),
        "--post-drain-observe-ms", str(item.get("post_drain_observe_ms", 0)),
        "--post-drain-sample-ms", str(item.get("post_drain_sample_ms", 100)),
        "--diagnostic-ready-file", str(ready_file),
    ]
    return command


def paired_entries(plan, policy, topology=None):
    blocks = {}
    for item in plan["runs"]:
        if item["policy"] != policy:
            continue
        if topology is not None and item["topology"] != topology:
            continue
        for repetition in range(1, int(item["repetitions"]) + 1):
            entry = dict(item)
            entry["repetition"] = repetition
            blocks.setdefault((item["block_id"], repetition), []).append(entry)
    keys = sorted(blocks)
    random.Random(plan["randomization_seed"]).shuffle(keys)
    ordered = []
    for index, key in enumerate(keys):
        matched = blocks[key]
        expected = len(plan.get("comparison_versions", [])) or 2
        if len(matched) != expected:
            raise SystemExit("refusing: matched block/repetition has %d arms; expected %d" % (len(matched), expected))
        random.Random(plan["randomization_seed"] + index + key[1]).shuffle(matched)
        ordered.extend(matched)
    return ordered


def host_state(expected_thp):
    one_node, node_spec = single_numa_node()
    return {
        "numa_balancing": read_text("/proc/sys/kernel/numa_balancing"),
        "numa_nodes_online": node_spec,
        "single_numa_node": one_node,
        "thp_mode": thp_mode(),
        "expected_thp_mode": expected_thp,
    }


def validate_host(state, numa_requirement="require-off"):
    reasons = []
    if state["numa_balancing"] != "0" and not (
            numa_requirement == "disabled-or-kernel-unsupported"
            and state["numa_balancing"] is None):
        reasons.append("NUMA balancing is not disabled")
    if not state["single_numa_node"]:
        reasons.append("host does not expose exactly one NUMA node")
    if state["thp_mode"] != state["expected_thp_mode"]:
        reasons.append("host THP mode differs from epoch policy")
    return reasons


def validate_frozen_item(item, actual_cpu):
    if item.get("cpu_list") != actual_cpu:
        raise ValueError("cpuset differs from frozen plan")
    library = pathlib.Path(item["allocator_library_path"])
    benchmark = pathlib.Path(item["benchmark_path"])
    if sha256_file(library) != item["allocator_library_sha256"]:
        raise ValueError("allocator library SHA-256 differs from frozen plan")
    if sha256_file(benchmark) != item["benchmark_sha256"]:
        raise ValueError("benchmark SHA-256 differs from frozen plan")
    return library, benchmark


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--topology", choices=("isolated", "service-like"), required=True,
                        help="one container/cpuset epoch runs one topology")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-runs", type=int, default=0)
    parser.add_argument("--sample-interval-ms", type=int, default=100)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if plan.get("design_status") != "Frozen" or not plan.get("experiment_id"):
        raise SystemExit("refusing: plan must have an experiment_id and design_status=Frozen")
    if args.sample_interval_ms <= 0:
        raise SystemExit("sample interval must be positive")
    unexpected = sorted(name for name in os.environ if name.startswith("MIMALLOC_"))
    if unexpected:
        raise SystemExit("refusing: unexpected inherited MIMALLOC_* variables: " + ", ".join(unexpected))

    policy_items = [
        item for item in plan["runs"]
        if item.get("policy") == args.policy and item.get("topology") == args.topology
    ]
    if not policy_items:
        raise SystemExit("refusing: plan has no runs for the requested policy/topology")
    expected_thp_modes = {item.get("host_thp") for item in policy_items}
    if len(expected_thp_modes) != 1 or None in expected_thp_modes:
        raise SystemExit("refusing: policy/topology must have one explicit host_thp mode")
    expected_thp = expected_thp_modes.pop()
    numa_requirement = plan.get("required_numa_balancing", "require-off")
    backpressure_policy = plan.get("backpressure_policy", "invalid-over-5pct")
    entries = paired_entries(plan, args.policy, args.topology)
    experiment_id = plan["experiment_id"]
    existing_raw_dir = ROOT / "results" / "raw" / experiment_id
    completed = set()
    for path in existing_raw_dir.glob("*.json"):
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if prior.get("valid"):
            completed.add((prior.get("block_id"), prior.get("repetition"),
                           prior.get("allocator_version")))
    entries = [entry for entry in entries
               if (entry["block_id"], entry["repetition"], entry["allocator_version"])
               not in completed]
    if args.max_runs:
        if args.max_runs % 2:
            raise SystemExit("--max-runs must be even so allocator pairs remain intact")
        entries = entries[:args.max_runs]
    if not args.execute:
        print(json.dumps({"dry_run": True, "policy": args.policy, "topology": args.topology,
                          "planned_runs": len(entries),
                          "expected_thp_mode": expected_thp,
                          "numa_balancing_required": numa_requirement},
                         sort_keys=True))
        return 0

    initial = host_state(expected_thp)
    initial_reasons = validate_host(initial, numa_requirement)
    if initial_reasons:
        raise SystemExit("refusing host-state epoch: " + "; ".join(initial_reasons))
    actual_cpu = allowed_cpu_list()
    raw_dir = ROOT / "results" / "raw" / experiment_id
    log_dir = ROOT / "results" / "logs" / experiment_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    environment_manifest = ROOT / "manifests/environment.json"
    environment_manifest_hash = sha256_file(environment_manifest) if environment_manifest.exists() else None

    for item in entries:
        pre = host_state(expected_thp)
        pre_reasons = validate_host(pre, numa_requirement)
        if pre_reasons:
            raise SystemExit("host state changed before run: " + "; ".join(pre_reasons))
        try:
            library, benchmark = validate_frozen_item(item, actual_cpu)
        except ValueError as error:
            raise SystemExit("refusing: " + str(error))

        run_id = str(uuid.uuid4())
        ready_file = log_dir / (run_id + ".pid")
        stdout_file = log_dir / (run_id + ".stdout.log")
        stderr_file = log_dir / (run_id + ".stderr.log")
        samples_file = log_dir / (run_id + ".memory.jsonl")
        command = command_for(item, ready_file)
        environment = {"PATH": os.environ["PATH"], "LD_PRELOAD": str(library)}
        for name, value in item.get("runtime_options", {}).items():
            key = name if name.startswith("MIMALLOC_") else "MIMALLOC_" + name.upper()
            environment[key] = str(value)
        process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, universal_newlines=True)
        samples, maximum_cgroup_peak = [], None
        sampled_pid = None
        cgroup_dirs, cgroup_before = None, None
        started = monotonic_ns()
        while process.poll() is None:
            if sampled_pid is None and ready_file.exists():
                try:
                    sampled_pid = int(ready_file.read_text(encoding="utf-8").strip())
                except (OSError, ValueError):
                    pass
            if sampled_pid is not None:
                if cgroup_dirs is None:
                    cgroup_dirs = cgroup_directories(sampled_pid)
                    cgroup_before = cgroup_snapshot(cgroup_dirs)
                sample = sample_process(sampled_pid, started)
                if sample is not None:
                    samples.append(sample)
                peak = cgroup_memory_peak(cgroup_dirs.get("memory") if cgroup_dirs else None)
                if peak is not None:
                    maximum_cgroup_peak = max(maximum_cgroup_peak or 0, peak)
            time.sleep(args.sample_interval_ms / 1000.0)
        stdout, stderr = process.communicate()
        cgroup_after = cgroup_snapshot(cgroup_dirs)
        stdout_file.write_text(stdout, encoding="utf-8")
        stderr_file.write_text(stderr, encoding="utf-8")
        samples_file.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in samples),
                                encoding="utf-8")
        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            output = {}
        reasons = []
        if process.returncode != 0 or output.get("valid") is not True:
            reasons.append("benchmark correctness validation failed")
        expected_library = str(library.resolve())
        actual_library = str(pathlib.Path(str(output.get("allocator_library_path", ""))).resolve())
        if actual_library != expected_library:
            reasons.append("loaded allocator path differs from frozen plan")
        expected_major = str(item["allocator_version"]).lstrip("v").split(".", 1)[0]
        if not str(output.get("allocator_version", "")).startswith(expected_major):
            reasons.append("detected allocator version differs from frozen plan")
        if (backpressure_policy == "invalid-over-5pct"
                and output.get("backpressure_ns", 0) > output.get("elapsed_ns", 0) * 0.05):
            reasons.append("aggregate queue backpressure exceeded 5% of elapsed time")
        if output.get("record_bank_saturation_count", 0) > 1:
            reasons.append("record banks were persistently saturated")
        before_cpu = (cgroup_before or {}).get("cpu_stat") or {}
        after_cpu = (cgroup_after or {}).get("cpu_stat") or {}
        if after_cpu.get("nr_throttled", 0) > before_cpu.get("nr_throttled", 0):
            reasons.append("cgroup CPU throttling occurred during the measured run")
        before_events = (cgroup_before or {}).get("memory_events") or {}
        after_events = (cgroup_after or {}).get("memory_events") or {}
        if after_events.get("oom", 0) > before_events.get("oom", 0):
            reasons.append("cgroup OOM occurred during the measured run")
        if (cgroup_after or {}).get("memory_swap_current") not in (None, 0):
            reasons.append("cgroup swap was in use")
        starts = output.get("worker_cpu_start", [])
        ends = output.get("worker_cpu_end", [])
        allowed = expand_cpu_list(actual_cpu)
        if item["topology"] == "isolated":
            expected = allowed[:item["thread_count"]]
            if starts != expected or ends != expected:
                reasons.append("isolated worker affinity differs from frozen mapping")
        else:
            expected_tcpio = allowed[::2][:item["tcpio_count"]]
            if starts[:item["tcpio_count"]] != expected_tcpio or ends[:item["tcpio_count"]] != expected_tcpio:
                reasons.append("service-like tcpio affinity differs from frozen mapping")
            if any(cpu not in allowed for cpu in starts + ends):
                reasons.append("service-like worker escaped the fixed cpuset")
        post = host_state(expected_thp)
        reasons.extend(validate_host(post, numa_requirement))
        rss_values = [sample["rss_bytes"] for sample in samples if sample["rss_bytes"] is not None]
        pss_values = [sample["pss_bytes"] for sample in samples if sample["pss_bytes"] is not None]
        hwm_values = [sample["vmhwm_bytes"] for sample in samples if sample["vmhwm_bytes"] is not None]
        huge_values = [sample["anon_huge_pages_bytes"] for sample in samples
                       if sample["anon_huge_pages_bytes"] is not None]
        record = {
            **item,
            **output,
            "experiment_id": experiment_id,
            "design_revision": plan["design_revision"],
            "environment_manifest_hash": environment_manifest_hash,
            "allocator_name": "mimalloc",
            "allocator_version": item["allocator_version"],
            "detected_allocator_version": output.get("allocator_version"),
            "build_profile": "release",
            "numa_nodes": [0],
            "numa_balancing_requirement": numa_requirement,
            "numa_balancing_observed": pre["numa_balancing"],
            "backpressure_policy": backpressure_policy,
            "backpressure_elapsed_ratio": (
                output.get("backpressure_ns", 0) / output["elapsed_ns"]
                if output.get("elapsed_ns") else None
            ),
            "thp_mode": expected_thp,
            "hugepage_mode": item.get("hugepage_mode", "unspecified"),
            "run_id": run_id,
            "repetition": item["repetition"],
            "timestamp": time.time(),
            "command": command,
            "exit_code": process.returncode,
            "valid": not reasons,
            "invalid_reason": "; ".join(dict.fromkeys(reasons)) if reasons else None,
            "host_state_before": pre,
            "host_state_after": post,
            "allocator_library_sha256": sha256_file(library),
            "benchmark_sha256": sha256_file(benchmark),
            "runtime_options": item.get("runtime_options", {}),
            "memory_sample_interval_ms": args.sample_interval_ms,
            "memory_sample_count": len(samples),
            "memory_samples_path": str(samples_file.relative_to(ROOT)),
            "stdout_path": str(stdout_file.relative_to(ROOT)),
            "stderr_path": str(stderr_file.relative_to(ROOT)),
            "benchmark_final_rss_bytes": output.get("peak_rss_bytes"),
            "peak_rss_bytes": max(rss_values) if rss_values else None,
            "peak_pss_bytes": max(pss_values) if pss_values else None,
            "peak_vmhwm_bytes": max(hwm_values) if hwm_values else None,
            "peak_anon_huge_pages_bytes": max(huge_values) if huge_values else None,
            "cgroup_peak_memory_bytes": maximum_cgroup_peak,
            "cgroup_before": cgroup_before,
            "cgroup_after": cgroup_after,
            "operations_per_second": (
                output.get("operation_count", 0) * 1e9 / output["elapsed_ns"]
                if output.get("elapsed_ns") else None
            ),
        }
        target = raw_dir / (run_id + ".json")
        target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if validate_host(host_state(expected_thp), numa_requirement):
            raise SystemExit("host state changed after raw record was preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
