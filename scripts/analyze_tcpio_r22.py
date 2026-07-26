#!/usr/bin/env python3
"""Paired r22 analysis. Never substitutes smoke/pilot data for final data."""
import argparse
import json
import pathlib
import random
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]


def ratio(v3, v2):
    return v3 / v2 if v2 not in (None, 0) else None


def metrics(record):
    operations = record["operation_count"]
    latency = record.get("latency_percentiles_ns", {})
    faults = record.get("page_faults", {})
    role_cpu = record.get("role_cpu_ns", {})
    return {
        "throughput": operations * 1e9 / record["elapsed_ns"],
        "p99_latency_ns": latency.get("p99"),
        "cpu_ns_per_operation": sum(role_cpu.get(role, 0) for role in ("tcpio", "policy", "record")) / operations,
        "system_cpu_ns": record.get("system_cpu_ns"),
        "faults": faults.get("minor", 0) + faults.get("major", 0),
        "peak_rss_bytes": record.get("peak_rss_bytes"),
        "backpressure_elapsed_ratio": record.get("backpressure_elapsed_ratio"),
    }


def bootstrap_ci(values, seed, iterations=10000):
    if not values:
        return None
    rng = random.Random(seed)
    estimates = []
    for _ in range(iterations):
        sample = [values[rng.randrange(len(values))] for _ in values]
        estimates.append(statistics.median(sample))
    estimates.sort()
    return [estimates[int(iterations * .025)], estimates[int(iterations * .975)]]


def describe(values, seed):
    ordered = sorted(values)
    quartiles = statistics.quantiles(ordered, n=4, method="inclusive") if len(ordered) > 1 else [ordered[0]] * 3
    mean = statistics.mean(ordered)
    standard_deviation = statistics.stdev(ordered) if len(ordered) > 1 else 0.0
    return {
        "n": len(ordered),
        "median": statistics.median(ordered),
        "mean": mean,
        "standard_deviation": standard_deviation,
        "coefficient_of_variation": standard_deviation / mean if mean else None,
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "p25": quartiles[0],
        "p75": quartiles[2],
        "iqr": quartiles[2] - quartiles[0],
        "median_bootstrap_95ci": bootstrap_ci(ordered, seed),
    }


def load_records(raw_dir):
    records = []
    for path in sorted(raw_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if record.get("experiment_id") == "r22":
            records.append(record)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=pathlib.Path, default=ROOT / "results/raw/r22")
    parser.add_argument("--output", type=pathlib.Path,
                        default=ROOT / "results/summaries/tcpio-r22.json")
    revision_group = parser.add_mutually_exclusive_group(required=True)
    revision_group.add_argument(
        "--design-revision",
        help="exact final revision; amendments are never pooled")
    revision_group.add_argument(
        "--isolated-revision",
        help="exact isolated revision for a topology-composite analysis")
    parser.add_argument(
        "--service-like-revision",
        help="exact service-like revision; required with --isolated-revision")
    args = parser.parse_args()
    if bool(args.isolated_revision) != bool(args.service_like_revision):
        parser.error("--isolated-revision and --service-like-revision must be used together")
    records = load_records(args.raw_dir)
    if args.design_revision:
        design_revisions = {"all": args.design_revision}
        revision_records = [
            record for record in records
            if record.get("design_revision") == args.design_revision
        ]
    else:
        design_revisions = {
            "isolated": args.isolated_revision,
            "service-like": args.service_like_revision,
        }
        revision_records = [
            record for record in records
            if (
                record.get("topology") == "isolated"
                and record.get("design_revision") == args.isolated_revision
            ) or (
                record.get("topology") == "service-like"
                and record.get("design_revision") == args.service_like_revision
            )
        ]
    final_records = [record for record in revision_records if record.get("run_kind") == "final"]
    if not final_records:
        summary = {
            "experiment_id": "r22",
            "execution_status": "Not executed",
            "reason": "No final measured records exist; smoke and pilot records are never pooled.",
            "raw_record_count": len(revision_records),
            "design_revisions": design_revisions,
            "final_record_count": 0,
            "decision": "unavailable",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(summary, sort_keys=True))
        return 0

    invalid = [record for record in final_records if not record.get("valid")]
    grouped = {}
    for record in final_records:
        if record.get("scenario") != "tcp_policy_record" or not record.get("valid"):
            continue
        key = (record["block_id"], record["repetition"])
        grouped.setdefault(key, {})[record["allocator_version"]] = record
    cell_ratios = {}
    descriptive_source = {}
    for (block_id, repetition), pair in grouped.items():
        if set(pair) != {"v2.1.2", "v3.4.3"}:
            continue
        v2, v3 = metrics(pair["v2.1.2"]), metrics(pair["v3.4.3"])
        descriptive_source.setdefault(block_id, {}).setdefault("v2.1.2", []).append(v2)
        descriptive_source.setdefault(block_id, {}).setdefault("v3.4.3", []).append(v3)
        cell = cell_ratios.setdefault(block_id, {})
        for name in v2:
            value = ratio(v3[name], v2[name])
            if value is not None:
                cell.setdefault(name, []).append(value)
    cells = []
    for index, (block_id, values) in enumerate(sorted(cell_ratios.items())):
        result = {"block_id": block_id, "descriptive": {}}
        for version, rows in descriptive_source.get(block_id, {}).items():
            result["descriptive"][version] = {}
            for metric_name in rows[0]:
                metric_values = [row[metric_name] for row in rows if row[metric_name] is not None]
                if metric_values:
                    result["descriptive"][version][metric_name] = describe(
                        metric_values, 0x22B10C + index)
        for name, samples in values.items():
            result[name + "_ratio_median"] = statistics.median(samples)
            result[name + "_ratio_paired_bootstrap_95ci"] = bootstrap_ci(samples, 0x22B10C + index)
            result[name + "_paired_count"] = len(samples)
        result["gate_pass"] = (
            result.get("throughput_ratio_median", 0) >= .97
            and result.get("p99_latency_ns_ratio_median", float("inf")) <= 1.05
            and result.get("cpu_ns_per_operation_ratio_median", float("inf")) <= 1.05
            and result.get("peak_rss_bytes_ratio_median", float("inf")) <= 1.10
        )
        cells.append(result)
    control_grouped = {}
    for record in revision_records:
        if record.get("run_kind") != "final-control" or not record.get("valid"):
            continue
        key = (record["block_id"], record["repetition"])
        control_grouped.setdefault(key, {})[record["allocator_version"]] = record
    control_values = {}
    for (block_id, _), pair in control_grouped.items():
        if set(pair) != {"v2.1.2", "v3.4.3"}:
            continue
        v2, v3 = metrics(pair["v2.1.2"]), metrics(pair["v3.4.3"])
        target = control_values.setdefault(block_id, {})
        for name in ("throughput", "cpu_ns_per_operation", "p99_latency_ns",
                     "peak_rss_bytes", "backpressure_elapsed_ratio"):
            value = ratio(v3.get(name), v2.get(name))
            if value is not None:
                target.setdefault(name, []).append(value)
    controls = []
    for index, (block_id, values) in enumerate(sorted(control_values.items())):
        result = {"block_id": block_id}
        for name, samples in values.items():
            result[name + "_ratio_median"] = statistics.median(samples)
            result[name + "_ratio_paired_bootstrap_95ci"] = bootstrap_ci(
                samples, 0x22C011 + index)
            result[name + "_paired_count"] = len(samples)
        controls.append(result)
    policy_gate = {}
    for policy in ("upstream-default", "normalized"):
        relevant = [cell for cell in cells if cell["block_id"].endswith("-" + policy)]
        policy_gate[policy] = bool(relevant) and all(cell["gate_pass"] for cell in relevant)
    correctness_failures = len(invalid)
    if correctness_failures:
        decision = "v2 유지"
    elif policy_gate["upstream-default"]:
        decision = "기본 업그레이드 적합"
    elif policy_gate["normalized"]:
        decision = "명시적 정책 조정 조건부 적합"
    else:
        decision = "v2 유지"
    summary = {
        "experiment_id": "r22",
        "design_revisions": design_revisions,
        "execution_status": "Executed",
        "scope": "single-NUMA tcpio pipeline; kernel CONFIG_NUMA_BALANCING unsupported",
        "final_record_count": len(final_records),
        "invalid_record_count": correctness_failures,
        "cells": cells,
        "controls": controls,
        "policy_gate": policy_gate,
        "decision": decision,
        "gate": {
            "throughput_v3_over_v2_min": .97,
            "p99_v3_over_v2_max": 1.05,
            "cpu_per_op_v3_over_v2_max": 1.05,
            "peak_rss_v3_over_v2_max": 1.10,
            "correctness_allocator_affinity_errors": 0,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": decision, "cells": len(cells)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
