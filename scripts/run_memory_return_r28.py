#!/usr/bin/env python3
"""Run only the isolated r28 memory-return comparison."""
import hashlib
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE_SPEC = importlib.util.spec_from_file_location(
    "active_runner_base", ROOT / "scripts" / "run_active_benchmark.py")
BASE = importlib.util.module_from_spec(BASE_SPEC)
BASE_SPEC.loader.exec_module(BASE)

BASE_CLI_FIELDS = BASE.CLI_FIELDS
BASE.CLI_FIELDS = BASE_CLI_FIELDS + (
    ("memory_return_mode", "--memory-return-mode"),
    ("memory_action_interval_ms", "--memory-action-interval-ms"),
    ("reallocate_after_observe", "--reallocate-after-observe"),
)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_base_validate_plan = BASE.validate_plan


def validate_plan(plan_path, plan):
    _base_validate_plan(plan_path, plan)
    if {block.get("profile") for block in plan.get("blocks", [])} != {"memory-return"}:
        raise ValueError("r28 runner accepts memory-return blocks only")
    if {block.get("scenario") for block in plan.get("blocks", [])} != {"memory_return"}:
        raise ValueError("r28 runner accepts the enhanced memory_return scenario only")
    dependencies = plan.get("runner", {}).get("dependencies", [])
    if not dependencies:
        raise ValueError("r28 runner dependencies are not frozen")
    for dependency in dependencies:
        path = ROOT / dependency["path"]
        if not path.is_file() or sha256_file(path) != dependency.get("sha256"):
            raise ValueError("runner dependency SHA-256 differs: " + dependency["path"])


_base_validate_output = BASE.validate_output


def validate_output(item, output, returncode, throttle_delta):
    failure = _base_validate_output(item, output, returncode, throttle_delta)
    if failure is not None:
        return failure
    required = (
        "rss_before_burst_bytes", "working_set_rss_bytes", "rss_after_free_bytes",
        "rss_after_idle_bytes", "rss_observations", "allocation_elapsed_ns",
        "free_elapsed_ns", "memory_action_count", "memory_action_elapsed_ns",
        "reallocation_count", "reallocation_elapsed_ns", "reallocation_minor_faults",
    )
    missing = [field for field in required if field not in output]
    if missing:
        return "enhanced memory output omitted fields: " + ", ".join(missing)
    if output.get("memory_return_mode") != item.get("memory_return_mode"):
        return "memory return mode differs from frozen plan"
    offsets = [sample.get("offset_ms") for sample in output.get("rss_observations", [])]
    if offsets != [0, 10, 100, 1000, 5000]:
        return "RSS observation schedule differs from frozen plan"
    expected_actions = 0
    if item["memory_return_mode"] == "collect-force":
        expected_actions = 1
    elif item["memory_return_mode"] in ("allocator-activity", "collect-normal"):
        expected_actions = int(item["idle_ms"]) // int(item["memory_action_interval_ms"]) + 1
    if int(output["memory_action_count"]) != expected_actions:
        return "memory action count differs from frozen plan"
    if int(output["reallocation_count"]) != int(item["expected_operation_count"]):
        return "reallocation count differs from frozen plan"
    return None


BASE.validate_plan = validate_plan
BASE.validate_output = validate_output


if __name__ == "__main__":
    raise SystemExit(BASE.main())
