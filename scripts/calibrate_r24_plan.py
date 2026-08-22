#!/usr/bin/env python3
"""Calibrate r24 counts from three complete repetitions of all three versions."""
import argparse, json, pathlib, statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSIONS = {212: "v2.1.2", 30403: "v3.4.3", 30500: "v3.5.0"}
TARGET_SECONDS = 15.0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-plan", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.pilot_plan.read_text(encoding="utf-8"))
    if plan.get("comparison_versions") != ["v2.1.2", "v3.4.3", "v3.5.0"]:
        raise SystemExit("not an r24 three-version pilot")
    blocks = {run["block_id"] for run in plan["runs"]}
    rows = []
    for path in (ROOT / "results/raw").glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("block_id") in blocks and row.get("valid"): rows.append(row)
    cells = []
    for block_id in sorted(blocks):
        selected = [r for r in rows if r["block_id"] == block_id]
        matched = {}
        for row in selected: matched.setdefault(row["repetition"], set()).add(VERSIONS.get(int(row["allocator_version"])))
        if len(selected) != 9 or len(matched) != 3 or any(v != set(VERSIONS.values()) for v in matched.values()):
            raise SystemExit(f"incomplete matched pilot cell: {block_id}")
        rates = [r["operation_count"] * 1e9 / r["elapsed_ns"] for r in selected]
        elapsed = [r["elapsed_ns"] / 1e9 for r in selected]
        original = selected[0]["operation_count"]
        calibrated = original if 10 <= statistics.median(elapsed) <= 30 else max(1_000_000, int(round(statistics.median(rates) * TARGET_SECONDS / 1_000_000) * 1_000_000))
        cells.append({"name": block_id.removeprefix("r24-pilot-"), "valid_records": 9,
            "matched_repetitions": 3, "pilot_operation_count": original,
            "combined_median_elapsed_seconds": statistics.median(elapsed),
            "combined_median_operations_per_second": statistics.median(rates),
            "core_operation_count": calibrated,
            "calibration_rule": "retain when combined median is 10-30s; otherwise all-version median rate * 15s, rounded to 1M"})
    result = {"schema_version": 1, "comparison_id": plan["comparison_id"],
              "source_plan": str(args.pilot_plan), "valid_pilot_records": len(rows),
              "target_seconds": TARGET_SECONDS, "cells": cells}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__": main()
