#!/usr/bin/env python3
"""Calibrate r23 core counts from complete paired pilot records."""
import argparse
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSIONS = {"v3.4.3", "v3.4.5"}
TARGET_SECONDS = 15.0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-plan", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.pilot_plan.read_text(encoding="utf-8"))
    expected_blocks = {run["block_id"] for run in plan["runs"]}
    rows = []
    for path in (ROOT / "results/raw").glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("block_id") in expected_blocks and row.get("valid"):
            rows.append(row)
    cells = []
    for block_id in sorted(expected_blocks):
        selected = [row for row in rows if row["block_id"] == block_id]
        pairs = {}
        for row in selected:
            pairs.setdefault(row["repetition"], {})[row["allocator_library_path"]] = row
        if len(selected) != 6 or len(pairs) != 3 or any(len(pair) != 2 for pair in pairs.values()):
            raise SystemExit(f"incomplete paired pilot cell: {block_id}")
        detected = {f"v{int(row['allocator_version']) // 10000}.{(int(row['allocator_version']) // 100) % 100}.{int(row['allocator_version']) % 100}" for row in selected}
        if detected != VERSIONS:
            raise SystemExit(f"unexpected versions in {block_id}: {detected}")
        rates = [row["operation_count"] * 1e9 / row["elapsed_ns"] for row in selected]
        elapsed = [row["elapsed_ns"] / 1e9 for row in selected]
        original = selected[0]["operation_count"]
        # Preserve an already compliant count; otherwise target 15 seconds and
        # round to one million operations for an auditable, version-neutral count.
        calibrated = original if 10.0 <= statistics.median(elapsed) <= 30.0 else int(round(statistics.median(rates) * TARGET_SECONDS / 1_000_000) * 1_000_000)
        prefix = next(iter(expected_blocks)).split("-pilot-", 1)[0] + "-pilot-"
        cells.append({"name": block_id.removeprefix(prefix),
                      "valid_records": len(selected), "paired_repetitions": len(pairs),
                      "pilot_operation_count": original,
                      "combined_median_elapsed_seconds": statistics.median(elapsed),
                      "combined_median_operations_per_second": statistics.median(rates),
                      "core_operation_count": calibrated,
                      "calibration_rule": "retain when median is 10-30s; otherwise combined-version median rate * 15s, rounded to 1M"})
    result = {"schema_version": 1, "comparison_id": plan["comparison_id"],
              "source_plan": str(args.pilot_plan), "valid_pilot_records": len(rows),
              "target_seconds": TARGET_SECONDS, "cells": cells}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
