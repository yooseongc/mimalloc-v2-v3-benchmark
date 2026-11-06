#!/usr/bin/env python3
"""Freeze r29 only after complete smoke and pilot evidence is present."""
import datetime
import hashlib
import json
import math
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT / "experiments/r29-v353-v1"
RAW = ROOT / "results/active/r29-v353-v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    path = DEST / "plan.json"
    plan = json.loads(path.read_text())
    if plan["design_status"] != "Draft":
        raise SystemExit("only a Draft plan can be frozen")
    draft_hash = sha(path)
    for stage, count in (("smoke", 39), ("pilot", 63)):
        rows = [json.loads(p.read_text()) for p in (RAW / stage / "raw").glob("*.json")]
        if len(rows) != count or any(not row["valid"] or row["plan_sha256"] != draft_hash for row in rows):
            raise SystemExit("complete valid " + stage + " evidence is required")
    pilot = rows
    calibration = []
    estimated_seconds = 0
    for block in plan["blocks"]:
        if block["profile"] == "memory-return":
            estimated_seconds += 15 * 3 * 6
            continue
        by_version = {}
        for version in plan["comparison_versions"]:
            values = [row["elapsed_ns"] / 1e9 for row in pilot
                      if row["block_id"] == block["block_id"] and row["allocator_version"] == version]
            if len(values) != 3:
                raise SystemExit("missing pilot triple")
            rates = [1 / value for value in values]
            by_version[version] = {"elapsed_seconds": values, "median_seconds": statistics.median(values),
                                   "throughput_cv": statistics.stdev(rates) / statistics.mean(rates)}
        fastest = min(v["median_seconds"] for v in by_version.values())
        scale = 10 / fastest
        old_count = block["operation_count"]
        block["operation_count"] = max(32, int(math.ceil(old_count * scale / 32)) * 32)
        if block.get("warmup_count", 0):
            block["warmup_count"] = block["operation_count"] // 100
        block["repetitions"] = 30 if max(v["throughput_cv"] for v in by_version.values()) > .10 else 15
        estimated_seconds += block["repetitions"] * sum(v["median_seconds"] * scale +
                                                       (5 if block["profile"] == "latency" else 0)
                                                       for v in by_version.values())
        calibration.append({"block_id": block["block_id"], "pilot": by_version,
                            "pilot_operation_count": old_count, "operation_count": block["operation_count"],
                            "repetitions": block["repetitions"]})
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report = {"frozen_at": now, "draft_plan_sha256": draft_hash,
              "estimated_measured_minutes": estimated_seconds / 60, "cells": calibration}
    (DEST / "calibration.json").write_bytes((json.dumps(report, indent=2) + "\n").encode("utf-8"))
    contract = (DEST / "contract.md").read_text()
    contract = contract.replace("Design status: Draft", "Design status: Frozen\nFrozen at: " + now)
    contract = contract.replace("None. Record pilot-driven calibration and freeze here before measured runs.",
        "2026-09-21: All 39 smoke and 63 core/latency pilot arms passed. Operation\n"
        "counts are scaled to ten seconds for the fastest version's pilot median,\n"
        "rounded upward to a multiple of 32. Cells exceeding 10% pilot throughput CV\n"
        "receive 30 repetitions; other cells receive 15. See calibration.json for\n"
        "all observations, counts and the resource estimate. Draft plan/contract\n"
        "copies preserve the exact smoke/pilot provenance. No measured data existed\n"
        "when these choices were made.\n\n"
        "Inherited-harness limitations established by source inspection before full\n"
        "measurement: local and remote core paths do not implement warm-up (zero\n"
        "is recorded); local timing includes small vector setup and thread joins;\n"
        "remote timing includes shared atomic checksum/count overhead. Memory-return\n"
        "is single-threaded within the fixed eight-CPU cpuset and does not pin its\n"
        "main thread to one particular CPU. Core/pipeline workers are pinned by the\n"
        "harness, but per-worker CPU observations are not exported in every scenario.\n"
        "These deviations are retained to use one unchanged historical binary and\n"
        "must be disclosed. Results describe these workloads, not pure allocator\n"
        "instruction cost. Only pipeline cells have explicit 1% warm-up.\n\n"
        "v3.5.3 enables statistics/profiling support and full THP preservation by\n"
        "default. Matching purge_delay alone is a one-variable policy comparison,\n"
        "not complete normalization of THP or instrumentation defaults. No fully\n"
        "normalized allocator-implementation claim is made. perf cycles/instructions\n"
        "and get_mempolicy are permission-denied; node 0 is the only allowed/exposed\n"
        "NUMA node. First-new diagnostics passed 1000 threads per version.\n\n"
        "Before measured runs, the r29 wrapper was hardened to decode byte output\n"
        "from subprocess timeouts before durable log writes. A regression test\n"
        "verifies timeout attempts remain recorded as invalid. Workload commands,\n"
        "timing and successful-output validation are unchanged. draft-runner.py\n"
        "preserves the smoke/pilot runner; the measured runner hash is frozen anew.")
    (DEST / "contract.md").write_bytes(contract.encode("utf-8"))
    # Frozen hashes must survive Git checkout on both Windows and Linux.
    artifacts = DEST / "artifacts.json"
    artifacts.write_bytes(artifacts.read_text(encoding="utf-8").encode("utf-8"))
    plan["design_status"] = "Frozen"
    plan["runner"]["sha256"] = sha(ROOT / "scripts/run_comparison_r29.py")
    plan["frozen_at"] = now
    plan["contract_sha256"] = sha(DEST / "contract.md")
    plan["calibration_sha256"] = sha(DEST / "calibration.json")
    plan["source_lock_sha256"] = sha(ROOT / "manifests/sources.lock")
    plan["artifacts_sha256"] = sha(DEST / "artifacts.json")
    plan["environment_sha256"] = sha(DEST / "environment.json")
    path.write_bytes((json.dumps(plan, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
