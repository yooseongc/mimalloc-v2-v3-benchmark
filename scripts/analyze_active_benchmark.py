#!/usr/bin/env python3
"""Analyze only complete matched repetitions from the isolated active run."""
import importlib.util
import json
import math
import pathlib
import random
import statistics
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "active_runner", ROOT / "scripts" / "run_active_benchmark.py")
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(RUNNER)


def describe(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "median": statistics.median(ordered),
        "mean": statistics.mean(ordered),
        "stdev": statistics.stdev(ordered) if len(ordered) > 1 else None,
        "cv": (statistics.stdev(ordered) / statistics.mean(ordered)
               if len(ordered) > 1 and statistics.mean(ordered) else None),
        "minimum": ordered[0],
        "p25": ordered[math.floor((len(ordered) - 1) * .25)],
        "p75": ordered[math.floor((len(ordered) - 1) * .75)],
        "maximum": ordered[-1],
    }


def bootstrap_median_ci(values: List[float], seed: int, samples: int = 10000) -> Optional[List[float]]:
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    medians = sorted(statistics.median(rng.choices(values, k=len(values))) for _ in range(samples))
    return [medians[math.floor((samples - 1) * .025)],
            medians[math.floor((samples - 1) * .975)]]


def latest_valid(raw_dir: pathlib.Path, comparison_id: str, revision: str) -> List[Dict[str, Any]]:
    selected: Dict[Tuple[str, int, str], Dict[str, Any]] = {}
    for path in raw_dir.glob("*.json") if raw_dir.exists() else ():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (record.get("comparison_id") != comparison_id or
                record.get("design_revision") != revision or
                record.get("valid") is not True):
            continue
        key = (record["block_id"], int(record["repetition"]), record["allocator_version"])
        if key not in selected or int(record.get("attempt", 1)) > int(selected[key].get("attempt", 1)):
            selected[key] = record
    return list(selected.values())


def complete_groups(rows: List[Dict[str, Any]], versions: List[str]) -> Dict[str, List[Dict[str, Dict[str, Any]]]]:
    grouped: Dict[Tuple[str, int], Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        grouped[(row["block_id"], int(row["repetition"]))][row["allocator_version"]] = row
    complete: Dict[str, List[Dict[str, Dict[str, Any]]]] = defaultdict(list)
    for (block_id, _), arms in grouped.items():
        if set(arms) == set(versions):
            complete[block_id].append(arms)
    return complete


def nested(record: Dict[str, Any], *keys: str) -> Optional[float]:
    value: Any = record
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def throughput(record: Dict[str, Any]) -> Optional[float]:
    elapsed = nested(record, "elapsed_ns")
    operations = nested(record, "operation_count")
    return operations * 1e9 / elapsed if elapsed and operations is not None else None


METRICS: Dict[str, Dict[str, Callable[[Dict[str, Any]], Optional[float]]]] = {
    "core": {
        "throughput_ops_per_second": throughput,
        "elapsed_ns": lambda r: nested(r, "elapsed_ns"),
        "peak_rss_bytes": lambda r: nested(r, "peak_rss_bytes"),
        "user_cpu_ns": lambda r: nested(r, "user_cpu_ns"),
        "system_cpu_ns": lambda r: nested(r, "system_cpu_ns"),
    },
    "memory-return": {
        "rss_after_free_bytes": lambda r: nested(r, "rss_after_free_bytes"),
        "rss_after_idle_bytes": lambda r: nested(r, "rss_after_idle_bytes"),
        "peak_rss_bytes": lambda r: nested(r, "peak_rss_bytes"),
    },
    "latency": {
        "throughput_ops_per_second": throughput,
        "p50_ns": lambda r: nested(r, "latency_percentiles_ns", "p50"),
        "p99_ns": lambda r: nested(r, "latency_percentiles_ns", "p99"),
        "p99_9_ns": lambda r: nested(r, "latency_percentiles_ns", "p99_9"),
        "peak_rss_bytes": lambda r: nested(r, "peak_rss_bytes"),
    },
}


def summarize(plan: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    versions = plan["comparison_versions"]
    groups = complete_groups(rows, versions)
    block_profiles = {block["block_id"]: block["profile"] for block in plan["blocks"]}
    result = []
    for block_id in sorted(block_profiles):
        triplets = groups.get(block_id, [])
        profile = block_profiles[block_id]
        metrics = []
        for metric_name, getter in METRICS[profile].items():
            by_version = {version: [getter(arms[version]) for arms in triplets] for version in versions}
            by_version = {version: [value for value in values if value is not None]
                          for version, values in by_version.items()}
            ratios = []
            for denominator, numerator in ((versions[0], versions[1]),
                                           (versions[0], versions[2]),
                                           (versions[1], versions[2])):
                values = []
                for arms in triplets:
                    left, right = getter(arms[denominator]), getter(arms[numerator])
                    if left not in (None, 0) and right is not None:
                        values.append(right / left)
                stable = int.from_bytes(f"{block_id}:{metric_name}:{denominator}:{numerator}".encode(), "little") % (2**32)
                ratios.append({"denominator": denominator, "numerator": numerator,
                               **describe(values), "median_95pct_bootstrap_ci":
                               bootstrap_median_ci(values, plan["randomization_seed"] + stable)})
            metrics.append({"metric": metric_name,
                            "by_version": {version: describe(values) for version, values in by_version.items()},
                            "matched_ratios": ratios})
        result.append({"block_id": block_id, "profile": profile,
                       "complete_matched_repetitions": len(triplets), "metrics": metrics})
    return {"comparison_id": plan["comparison_id"],
            "design_revision": plan["design_revision"],
            "comparison_versions": versions,
            "valid_unique_records": len(rows),
            "complete_matched_repetitions": sum(len(value) for value in groups.values()),
            "blocks": result}


def main() -> int:
    _, plan = RUNNER.active_plan()
    result_root = ROOT / "results" / "active" / plan["result_namespace"] / "measured"
    rows = latest_valid(result_root / "raw", plan["comparison_id"], plan["design_revision"])
    summary = summarize(plan, rows)
    summary["execution_status"] = "Not executed" if not rows else "Partial or complete; inspect block counts"
    output = result_root / "summary.json"
    RUNNER.atomic_json(output, summary)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
