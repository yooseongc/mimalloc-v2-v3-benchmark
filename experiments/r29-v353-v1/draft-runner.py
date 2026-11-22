#!/usr/bin/env python3
"""Run r29 smoke, pilot and measured stages without modifying historical runners."""
import argparse
import copy
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "memory_runner_r28", ROOT / "scripts/run_memory_return_r28.py")
MEMORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MEMORY)
BASE = MEMORY.BASE


def validate_output(item, output, returncode, throttle_delta):
    validator = (MEMORY.validate_output if item["scenario"] == "memory_return"
                 else MEMORY._base_validate_output)
    failure = validator(item, output, returncode, throttle_delta)
    if failure is None and item.get("measurement_stage") == "measured":
        if item["profile"] in ("core", "latency") and output["elapsed_ns"] < 5e9:
            return "measured duration below predeclared five-second minimum"
    return failure


BASE.validate_output = validate_output


def validate_plan(path, plan, stage):
    if plan["comparison_id"] != "r29-v353-v1":
        raise ValueError("r29 runner requires r29-v353-v1")
    if plan["design_status"] not in ("Draft", "Frozen"):
        raise ValueError("unknown design status")
    if stage == "measured" and plan["design_status"] != "Frozen":
        raise ValueError("measured runs require a frozen design")
    checking = dict(plan, design_status="Frozen")
    MEMORY._base_validate_plan(path, checking)
    for dependency in plan["runner"]["dependencies"]:
        if BASE.sha256_file(ROOT / dependency["path"]) != dependency["sha256"]:
            raise ValueError("frozen runner dependency changed: " + dependency["path"])


def entries_for(plan, profiles, stage):
    effective = copy.deepcopy(plan)
    if stage == "pilot":
        for block in effective["blocks"]:
            block["repetitions"] = 3
    entries = BASE.expand_entries(effective, profiles, "smoke" if stage == "smoke" else "measured")
    for item in entries:
        item["measurement_stage"] = stage
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("smoke", "pilot", "measured"), default="measured")
    parser.add_argument("--profile", action="append", choices=("core", "memory-return", "latency"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--max-blocks", type=int, default=1)
    args = parser.parse_args()
    path, plan = BASE.active_plan()
    validate_plan(path, plan, args.stage)
    entries = entries_for(plan, set(args.profile or ("core", "memory-return", "latency")), args.stage)
    destination = ROOT / "results/active" / plan["result_namespace"] / args.stage
    raw = destination / "raw"
    if args.status:
        BASE.print_status(plan, entries, raw)
        return 0
    if not args.execute:
        done, _ = BASE.prior_state(raw)
        blocks = BASE.scheduled_blocks(entries, done, plan["randomization_seed"], args.max_blocks)
        print(json.dumps({"stage": args.stage, "pending_blocks": len(blocks),
                          "commands": [[BASE.command_for(item) for item in block] for block in blocks]}, indent=2))
        return 0
    with BASE.execution_lock(destination):
        digest = BASE.sha256_file(path)
        done, attempts = BASE.prior_state(raw)
        # Reject namespace contamination even when resume would otherwise skip it.
        for old in raw.glob("*.json") if raw.exists() else ():
            if json.loads(old.read_text())["plan_sha256"] != digest:
                raise ValueError("plan hash differs from existing stage records; use a new namespace")
        audit = BASE.preflight(plan, digest)
        audit_path = destination / "audits" / ("preflight-" + BASE.dt.datetime.now().strftime("%Y%m%dT%H%M%S%f") + ".json")
        BASE.atomic_json(audit_path, audit)
        if not audit["valid"]:
            print(json.dumps(audit), flush=True)
            return 2
        blocks = BASE.scheduled_blocks(entries, done, plan["randomization_seed"], args.max_blocks)
        for block in blocks:
            failed = False
            for item in block:
                identity = BASE.run_identity(item)
                record = BASE.execute_one(item, attempts.get(identity, 0) + 1,
                                          raw, destination / "logs", digest)
                print(json.dumps({"run_id": record["run_id"], "valid": record["valid"],
                                  "elapsed_s": record.get("elapsed_ns", 0) / 1e9,
                                  "invalid_reason": record["invalid_reason"]}), flush=True)
                failed = failed or not record["valid"]
            if failed:
                return 1
    BASE.print_status(plan, entries, raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
