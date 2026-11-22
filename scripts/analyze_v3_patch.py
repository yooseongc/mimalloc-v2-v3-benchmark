#!/usr/bin/env python3
"""Analyze only complete paired records from the frozen r23a core plan."""
import argparse
import json
import math
import pathlib
import re
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]

def percentile(values, fraction):
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower, upper = math.floor(index), math.ceil(index)
    return ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

def describe(values):
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else None
    half = 1.96 * stdev / math.sqrt(len(values)) if stdev is not None else None
    return {"count": len(values), "median": statistics.median(values), "mean": mean,
            "stdev": stdev, "coefficient_of_variation": stdev / mean if stdev is not None and mean else None,
            "minimum": min(values), "maximum": max(values), "p25": percentile(values, .25),
            "p75": percentile(values, .75), "iqr": percentile(values, .75) - percentile(values, .25),
            "mean_95ci_normal": [mean - half, mean + half] if half is not None else None}

def version(row):
    match = re.search(r"mimalloc-(v\d+\.\d+\.\d+)", row["allocator_library_path"])
    if not match:
        raise SystemExit("cannot resolve semantic allocator version")
    return match.group(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if plan.get("design_status") != "Frozen" or plan.get("calibration_status") != "complete":
        raise SystemExit("refusing non-frozen or uncalibrated plan")
    versions = tuple(plan["comparison_versions"])
    blocks = {run["block_id"] for run in plan["runs"]}
    rows = []
    for path in (ROOT / "results/raw").glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("block_id") in blocks:
            rows.append(row)
    if len(rows) != 150 or any(not row.get("valid") for row in rows):
        raise SystemExit("r23a core must contain exactly 150 valid records")
    cells = []
    for block in sorted(blocks):
        selected = [row for row in rows if row["block_id"] == block]
        pairs = {}
        for row in selected:
            pairs.setdefault(row["repetition"], {})[version(row)] = row
        if len(pairs) != 15 or any(set(pair) != set(versions) for pair in pairs.values()):
            raise SystemExit(f"incomplete pair set: {block}")
        by_version = {}
        for allocator_version in versions:
            vr = [row for row in selected if version(row) == allocator_version]
            by_version[allocator_version] = {
                "throughput_ops_per_second": describe([row["operation_count"] * 1e9 / row["elapsed_ns"] for row in vr]),
                "elapsed_seconds": describe([row["elapsed_ns"] / 1e9 for row in vr]),
                "peak_rss_bytes": describe([row["peak_rss_bytes"] for row in vr]),
                "cpu_seconds": describe([(row.get("user_cpu_ns", 0) + row.get("system_cpu_ns", 0)) / 1e9 for row in vr]),
                "minor_faults": describe([row["page_faults"]["minor"] for row in vr]),
                "major_faults_total": sum(row["page_faults"]["major"] for row in vr),
            }
        ratios = {"throughput": [], "elapsed": [], "peak_rss": [], "cpu_seconds": []}
        for pair in pairs.values():
            old, new = pair[versions[0]], pair[versions[1]]
            ratios["throughput"].append(old["elapsed_ns"] / new["elapsed_ns"])
            ratios["elapsed"].append(new["elapsed_ns"] / old["elapsed_ns"])
            ratios["peak_rss"].append(new["peak_rss_bytes"] / old["peak_rss_bytes"])
            old_cpu = old.get("user_cpu_ns", 0) + old.get("system_cpu_ns", 0)
            new_cpu = new.get("user_cpu_ns", 0) + new.get("system_cpu_ns", 0)
            ratios["cpu_seconds"].append(new_cpu / old_cpu)
        cells.append({"block_id": block, "paired_repetitions": len(pairs),
                      "by_version": by_version,
                      "ratios_v3.4.5_over_v3.4.3": {name: describe(values) for name, values in ratios.items()}})
    result = {"schema_version": 1, "comparison_id": plan["comparison_id"],
              "analysis_scope": str(args.plan), "valid_records": len(rows),
              "comparison_versions": versions, "ratio_direction": "v3.4.5 / v3.4.3",
              "confidence_interval": "normal approximation for the mean across 15 paired repetitions",
              "cells": cells}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
