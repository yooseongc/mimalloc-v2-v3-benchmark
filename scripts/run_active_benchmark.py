#!/usr/bin/env python3
"""Run the isolated active benchmark in resumable matched blocks.

Historical runners remain available for reproducing historical epochs.  This
runner deliberately accepts no arbitrary plan path: experiments/ACTIVE is the
only entry point, preventing an old manifest from being mixed into new data.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import pathlib
import random
import re
import subprocess
import sys
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACTIVE_FILE = ROOT / "experiments" / "ACTIVE"
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


@contextlib.contextmanager
def execution_lock(result_root: pathlib.Path):
    """Prevent two runners from choosing and overwriting the same attempt."""
    result_root.mkdir(parents=True, exist_ok=True)
    stream = (result_root / ".runner.lock").open("a+", encoding="utf-8")
    try:
        try:
            import fcntl  # Linux measurement container only
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError as error:
            raise RuntimeError("execution locking requires the Linux measurement container") from error
        except BlockingIOError as error:
            raise RuntimeError("another active benchmark runner holds this result namespace") from error
        stream.seek(0)
        stream.truncate()
        stream.write(json.dumps({"pid": os.getpid(), "locked_at": iso_now()}) + "\n")
        stream.flush()
        yield
    finally:
        try:
            if "fcntl" in locals():
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()


def active_plan() -> Tuple[pathlib.Path, Dict[str, Any]]:
    experiment_id = ACTIVE_FILE.read_text(encoding="utf-8").strip()
    if not SAFE_ID.fullmatch(experiment_id):
        raise ValueError("experiments/ACTIVE contains an unsafe experiment id")
    plan_path = ROOT / "experiments" / experiment_id / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("comparison_id") != experiment_id:
        raise ValueError("ACTIVE id and plan comparison_id differ")
    return plan_path, plan


def canonical_cpu_list(value: Optional[str]) -> Optional[Tuple[int, ...]]:
    if value is None:
        return None
    cpus: Set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            left, right = (int(x) for x in part.split("-", 1))
            if right < left:
                raise ValueError("descending CPU range")
            cpus.update(range(left, right + 1))
        else:
            cpus.add(int(part))
    return tuple(sorted(cpus))


def proc_status_list(name: str) -> Optional[str]:
    try:
        for line in pathlib.Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith(name + ":"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def active_thp_mode() -> Optional[str]:
    path = pathlib.Path("/sys/kernel/mm/transparent_hugepage/enabled")
    try:
        match = re.search(r"\[([^]]+)\]", path.read_text(encoding="utf-8"))
        return match.group(1) if match else None
    except OSError:
        return None


def read_cpu_stat() -> Optional[Dict[str, int]]:
    candidates = (pathlib.Path("/sys/fs/cgroup/cpu.stat"),
                  pathlib.Path("/sys/fs/cgroup/cpu/cpu.stat"))
    for path in candidates:
        try:
            result: Dict[str, int] = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                key, value = line.split()[:2]
                result[key] = int(value)
            return result
        except (OSError, ValueError):
            continue
    return None


def validate_plan(plan_path: pathlib.Path, plan: Dict[str, Any]) -> None:
    if plan.get("schema_version") != 3:
        raise ValueError("active plan schema_version must be 3")
    if plan.get("design_status") != "Frozen":
        raise ValueError("active plan must have design_status=Frozen")
    if not SAFE_ID.fullmatch(str(plan.get("result_namespace", ""))):
        raise ValueError("result_namespace is missing or unsafe")
    contract = ROOT / str(plan["contract_path"])
    if sha256_file(contract) != plan.get("contract_sha256"):
        raise ValueError("measurement contract SHA-256 differs from frozen plan")
    frozen_runner = ROOT / str(plan["runner"]["path"])
    if sha256_file(frozen_runner) != plan["runner"].get("sha256"):
        raise ValueError("active runner SHA-256 differs from frozen plan; create a new revision")
    versions = [item.get("version") for item in plan.get("allocators", [])]
    if versions != plan.get("comparison_versions") or len(set(versions)) != len(versions):
        raise ValueError("allocator list must exactly match comparison_versions")
    block_ids = [item.get("block_id") for item in plan.get("blocks", [])]
    if not block_ids or len(set(block_ids)) != len(block_ids):
        raise ValueError("block ids must be present and unique")
    if any(not SAFE_ID.fullmatch(str(value)) for value in block_ids):
        raise ValueError("block id is unsafe")
    if plan_path.parent.name != plan["comparison_id"]:
        raise ValueError("plan must live in its comparison_id directory")


def expand_entries(plan: Dict[str, Any], profiles: Set[str], stage: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    environment = plan["environment"]
    defaults = plan.get("block_defaults", {})
    for specific in plan["blocks"]:
        block = {**defaults, **specific}
        if block["profile"] not in profiles:
            continue
        repetitions = 1 if stage == "smoke" else int(block["repetitions"])
        for repetition in range(1, repetitions + 1):
            for allocator in plan["allocators"]:
                item = {**block, **allocator,
                        "comparison_id": plan["comparison_id"],
                        "design_revision": plan["design_revision"],
                        "repetition": repetition,
                        "cpu_list": environment["cpu_list"],
                        "numa_nodes": environment["numa_nodes"],
                        "thp_mode": environment["thp_mode"],
                        "benchmark_path": plan["benchmark"]["path"],
                        "benchmark_sha256": plan["benchmark"]["sha256"],
                        "timeout_seconds": environment["timeout_seconds"]}
                if stage == "smoke":
                    item["operation_count"] = int(block["smoke_operation_count"])
                    item["warmup_count"] = int(block.get("smoke_warmup_count", 0))
                entries.append(item)
    return entries


def run_identity(item: Dict[str, Any]) -> Tuple[str, int, str]:
    return item["block_id"], int(item["repetition"]), item["version"]


def run_slug(item: Dict[str, Any]) -> str:
    return f"{item['block_id']}--r{int(item['repetition']):03d}--{item['version']}"


def prior_state(raw_dir: pathlib.Path) -> Tuple[Set[Tuple[str, int, str]], Dict[Tuple[str, int, str], int]]:
    valid: Set[Tuple[str, int, str]] = set()
    attempts: Dict[Tuple[str, int, str], int] = defaultdict(int)
    if not raw_dir.exists():
        return valid, attempts
    for path in raw_dir.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            identity = (record["block_id"], int(record["repetition"]), record["allocator_version"])
            attempts[identity] = max(attempts[identity], int(record.get("attempt", 1)))
            if record.get("valid") is True:
                valid.add(identity)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return valid, attempts


def scheduled_blocks(entries: Iterable[Dict[str, Any]], completed: Set[Tuple[str, int, str]],
                     seed: int, max_blocks: int) -> List[List[Dict[str, Any]]]:
    entries = list(entries)
    expected_arms = len({entry["version"] for entry in entries})
    grouped: Dict[Tuple[str, int], List[Dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        if run_identity(entry) not in completed:
            grouped[(entry["block_id"], int(entry["repetition"]))].append(entry)
    # A resumed partial triplet is completed before an unrelated block.  Full
    # pending blocks retain their seeded randomized order.
    partial = sorted(key for key, block in grouped.items() if len(block) < expected_arms)
    full = sorted(key for key, block in grouped.items() if len(block) == expected_arms)
    random.Random(seed).shuffle(partial)
    random.Random(seed).shuffle(full)
    keys = partial + full
    if max_blocks > 0:
        keys = keys[:max_blocks]
    result = []
    for block_id, repetition in keys:
        block = grouped[(block_id, repetition)]
        stable = int(hashlib.sha256(block_id.encode("utf-8")).hexdigest()[:8], 16)
        random.Random(seed + stable + repetition).shuffle(block)
        result.append(block)
    return result


CLI_FIELDS = (
    ("scenario", "--scenario"), ("operation_count", "--operations"),
    ("thread_count", "--threads"), ("size_bytes", "--size"),
    ("size_profile", "--size-profile"), ("batch_size", "--batch-size"),
    ("free_order", "--free-order"), ("touch_mode", "--touch-mode"),
    ("allocation_api", "--allocation-api"), ("idle_ms", "--idle-ms"),
    ("producer_count", "--producers"), ("consumer_count", "--consumers"),
    ("queue_capacity", "--queue-capacity"), ("tcpio_count", "--tcpio"),
    ("policy_count", "--policy"), ("record_count", "--record"),
    ("return_queue_capacity", "--return-queue-capacity"),
    ("record_queue_capacity", "--record-queue-capacity"),
    ("record_bank_bytes", "--record-bank-bytes"),
    ("record_bank_items", "--record-bank-items"),
    ("payload_profile", "--payload-profile"), ("stage_work", "--stage-work"),
    ("topology", "--topology"), ("warmup_count", "--warmup-count"),
    ("seed", "--seed"), ("latency_sample_rate", "--latency-sample-rate"),
    ("post_drain_observe_ms", "--post-drain-observe-ms"),
    ("post_drain_sample_ms", "--post-drain-sample-ms"),
)


def command_for(item: Dict[str, Any]) -> List[str]:
    command = [str(pathlib.Path(item["benchmark_path"]).resolve())]
    for field, option in CLI_FIELDS:
        if field in item and item[field] is not None:
            command.extend((option, str(item[field])))
    return command


def preflight(plan: Dict[str, Any], plan_digest: str) -> Dict[str, Any]:
    expected_cpu = canonical_cpu_list(plan["environment"]["cpu_list"])
    expected_mems = tuple(int(x) for x in plan["environment"]["numa_nodes"])
    actual_cpu_text = proc_status_list("Cpus_allowed_list")
    actual_mems_text = proc_status_list("Mems_allowed_list")
    errors: List[str] = []
    if canonical_cpu_list(actual_cpu_text) != expected_cpu:
        errors.append(f"cpuset mismatch: expected {plan['environment']['cpu_list']}, got {actual_cpu_text}")
    if canonical_cpu_list(actual_mems_text) != expected_mems:
        errors.append(f"NUMA mems mismatch: expected {expected_mems}, got {actual_mems_text}")
    actual_thp = active_thp_mode()
    if actual_thp != plan["environment"]["thp_mode"]:
        errors.append(f"THP mismatch: expected {plan['environment']['thp_mode']}, got {actual_thp}")
    artifacts = [(plan["benchmark"]["path"], plan["benchmark"]["sha256"])]
    artifacts.extend((item["library_path"], item["library_sha256"]) for item in plan["allocators"])
    artifact_checks = []
    for text_path, expected in artifacts:
        path = pathlib.Path(text_path)
        actual = sha256_file(path) if path.is_file() else None
        artifact_checks.append({"path": text_path, "expected_sha256": expected, "actual_sha256": actual})
        if actual != expected:
            errors.append(f"artifact SHA-256 mismatch: {text_path}")
    unexpected = sorted(name for name in os.environ if name.startswith("MIMALLOC_"))
    if unexpected:
        errors.append("unexpected inherited MIMALLOC_* variables: " + ", ".join(unexpected))
    return {"timestamp": iso_now(), "plan_sha256": plan_digest, "valid": not errors,
            "errors": errors, "actual_cpu_list": actual_cpu_text,
            "actual_numa_mems": actual_mems_text, "actual_thp_mode": actual_thp,
            "artifact_checks": artifact_checks}


def result_environment(item: Dict[str, Any]) -> Dict[str, str]:
    env = {"PATH": os.environ.get("PATH", ""), "LD_PRELOAD": item["library_path"]}
    for name, value in item.get("runtime_options", {}).items():
        key = name if name.startswith("MIMALLOC_") else "MIMALLOC_" + name.upper()
        env[key] = str(value)
    return env


def validate_output(item: Dict[str, Any], output: Dict[str, Any], returncode: int,
                    throttle_delta: Optional[int]) -> Optional[str]:
    if returncode != 0:
        return f"benchmark exit code {returncode}"
    if output.get("valid") is not True:
        return "benchmark reported invalid"
    required = ("allocator_version", "allocator_library_path", "elapsed_ns", "operation_count", "checksum")
    missing = [field for field in required if field not in output]
    if missing:
        return "benchmark omitted fields: " + ", ".join(missing)
    if int(output["allocator_version"]) != int(item["mi_version"]):
        return "detected allocator version differs from frozen plan"
    expected_library = pathlib.Path(item["library_path"]).resolve()
    if pathlib.Path(str(output["allocator_library_path"])).resolve() != expected_library:
        return "loaded allocator library differs from frozen plan"
    expected_operations = int(item.get("expected_operation_count", item["operation_count"]))
    if int(output["operation_count"]) != expected_operations:
        return "completed operation count differs from frozen plan"
    if throttle_delta is not None and throttle_delta > 0:
        return f"cgroup CPU throttling occurred ({throttle_delta} events)"
    return None


def execute_one(item: Dict[str, Any], attempt: int, raw_dir: pathlib.Path,
                log_dir: pathlib.Path, plan_digest: str) -> Dict[str, Any]:
    slug = run_slug(item)
    command = command_for(item)
    stdout_path = log_dir / f"{slug}--a{attempt:03d}.stdout"
    stderr_path = log_dir / f"{slug}--a{attempt:03d}.stderr"
    before = read_cpu_stat()
    began = iso_now()
    returncode = -1
    stdout = ""
    stderr = ""
    failure: Optional[str] = None
    try:
        completed = subprocess.run(command, env=result_environment(item), universal_newlines=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=int(item["timeout_seconds"]), check=False)
        returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        failure = f"timeout after {item['timeout_seconds']} seconds"
    except OSError as error:
        failure = f"could not start benchmark: {error}"
        stderr = str(error)
    after = read_cpu_stat()
    atomic_text(stdout_path, stdout)
    atomic_text(stderr_path, stderr)
    output: Dict[str, Any] = {}
    if failure is None:
        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            failure = "benchmark did not emit exactly one JSON object"
    throttle_delta = None
    if before is not None and after is not None:
        throttle_delta = after.get("nr_throttled", 0) - before.get("nr_throttled", 0)
    if failure is None:
        failure = validate_output(item, output, returncode, throttle_delta)
    record = {**item, **output, "allocator_version": item["version"],
              "allocator_commit": item["commit"], "run_id": slug,
              "attempt": attempt, "timestamp": began, "completed_at": iso_now(),
              "command": command, "exit_code": returncode,
              "stdout_path": str(stdout_path.relative_to(ROOT)),
              "stderr_path": str(stderr_path.relative_to(ROOT)),
              "plan_sha256": plan_digest, "cpu_stat_before": before,
              "cpu_stat_after": after, "cpu_throttle_delta": throttle_delta,
              "valid": failure is None, "invalid_reason": failure}
    target = raw_dir / f"{slug}--a{attempt:03d}.json"
    atomic_json(target, record)
    return record


def print_status(plan: Dict[str, Any], entries: List[Dict[str, Any]], raw_dir: pathlib.Path) -> None:
    completed, attempts = prior_state(raw_dir)
    all_ids = {run_identity(item) for item in entries}
    by_profile: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "valid": 0})
    for item in entries:
        profile = item["profile"]
        by_profile[profile]["total"] += 1
        by_profile[profile]["valid"] += int(run_identity(item) in completed)
    summary = {"comparison_id": plan["comparison_id"], "result_directory": str(raw_dir),
               "total": len(all_ids), "valid": len(all_ids & completed),
               "pending": len(all_ids - completed), "attempted_runs": sum(attempts.values()),
               "profiles": dict(sorted(by_profile.items()))}
    print(json.dumps(summary, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("smoke", "measured"), default="measured")
    parser.add_argument("--profile", action="append", choices=("core", "memory-return", "latency"),
                        help="repeat to select profiles; defaults to all for status/dry-run")
    parser.add_argument("--execute", action="store_true", help="execute; omission is a dry-run")
    parser.add_argument("--status", action="store_true", help="print isolated active-result status")
    parser.add_argument("--max-blocks", type=int, default=1,
                        help="matched blocks per invocation; 0 explicitly selects all pending blocks")
    args = parser.parse_args()
    plan_path, plan = active_plan()
    validate_plan(plan_path, plan)
    plan_digest = sha256_file(plan_path)
    profiles = set(args.profile or ("core", "memory-return", "latency"))
    entries = expand_entries(plan, profiles, args.stage)
    result_root = ROOT / "results" / "active" / plan["result_namespace"] / args.stage
    raw_dir, log_dir = result_root / "raw", result_root / "logs"
    if args.status:
        print_status(plan, entries, raw_dir)
        return 0
    completed, attempts = prior_state(raw_dir)
    blocks = scheduled_blocks(entries, completed, int(plan["randomization_seed"]), args.max_blocks)
    if not args.execute:
        print(json.dumps({"comparison_id": plan["comparison_id"], "stage": args.stage,
                          "profiles": sorted(profiles), "pending_blocks_selected": len(blocks),
                          "commands": [[{"allocator_version": item["version"],
                                         "command": command_for(item)} for item in block]
                                       for block in blocks]}, indent=2))
        return 0
    try:
        with execution_lock(result_root):
            # Re-read after acquiring the lock in case a preceding runner just
            # completed work between scheduling and lock acquisition.
            completed, attempts = prior_state(raw_dir)
            blocks = scheduled_blocks(entries, completed, int(plan["randomization_seed"]), args.max_blocks)
            audit = preflight(plan, plan_digest)
            audit_path = result_root / "audits" / ("preflight-" + dt.datetime.now().strftime("%Y%m%dT%H%M%S%f") + ".json")
            atomic_json(audit_path, audit)
            if not audit["valid"]:
                print("preflight failed; no benchmark record was started", file=sys.stderr)
                for error in audit["errors"]:
                    print("- " + error, file=sys.stderr)
                return 2
            invalid = 0
            for block in blocks:
                for item in block:
                    identity = run_identity(item)
                    attempt = attempts.get(identity, 0) + 1
                    record = execute_one(item, attempt, raw_dir, log_dir, plan_digest)
                    attempts[identity] = attempt
                    invalid += int(not record["valid"])
                    print(json.dumps({"run_id": record["run_id"], "attempt": attempt,
                                      "valid": record["valid"], "invalid_reason": record["invalid_reason"]}))
    except KeyboardInterrupt:
        print("interrupted; completed records are durable and the next invocation resumes the block", file=sys.stderr)
        return 130
    except RuntimeError as error:
        print(f"refusing: {error}", file=sys.stderr)
        return 2
    print_status(plan, entries, raw_dir)
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
