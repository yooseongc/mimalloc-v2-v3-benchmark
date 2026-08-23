#!/usr/bin/env python3
"""Analyze complete matched r28 memory-return triplets and mode effects."""
import hashlib
import importlib.util
import json
import math
import pathlib
import random
import statistics
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "memory_runner", ROOT / "scripts" / "run_memory_return_r28.py")
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(RUNNER)


def describe(values):
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    mean = statistics.mean(ordered)
    return {
        "count": len(ordered),
        "median": statistics.median(ordered),
        "mean": mean,
        "stdev": statistics.stdev(ordered) if len(ordered) > 1 else None,
        "cv": statistics.stdev(ordered) / mean if len(ordered) > 1 and mean else None,
        "minimum": ordered[0],
        "p25": ordered[math.floor((len(ordered) - 1) * .25)],
        "p75": ordered[math.floor((len(ordered) - 1) * .75)],
        "maximum": ordered[-1],
    }


def stable_seed(text):
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def bootstrap_median_ci(values, seed, samples=10000):
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    medians = sorted(statistics.median(rng.choices(values, k=len(values)))
                     for _ in range(samples))
    return [medians[math.floor((samples - 1) * .025)],
            medians[math.floor((samples - 1) * .975)]]


def latest_valid(raw_dir, plan):
    selected = {}
    for path in raw_dir.glob("*.json") if raw_dir.exists() else ():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (record.get("comparison_id") != plan["comparison_id"] or
                record.get("design_revision") != plan["design_revision"] or
                record.get("valid") is not True):
            continue
        key = (record["block_id"], int(record["repetition"]), record["allocator_version"])
        if key not in selected or int(record.get("attempt", 1)) > int(selected[key].get("attempt", 1)):
            selected[key] = record
    return selected


def rss_at(record, offset):
    for sample in record.get("rss_observations", []):
        if int(sample.get("offset_ms", -1)) == offset:
            return float(sample["rss_bytes"])
    return None


def retained_fraction(record, offset):
    baseline = float(record["rss_before_burst_bytes"])
    working = float(record["working_set_rss_bytes"])
    observed = rss_at(record, offset)
    denominator = working - baseline
    if observed is None or denominator <= 0:
        return None
    return (observed - baseline) / denominator


def returned_fraction(record, offset):
    retained = retained_fraction(record, offset)
    return None if retained is None else 1.0 - retained


def value(record, name):
    if name.startswith("rss_at_"):
        return rss_at(record, int(name.split("_")[-1]))
    if name.startswith("retained_fraction_"):
        return retained_fraction(record, int(name.split("_")[-1]))
    if name.startswith("returned_fraction_"):
        return returned_fraction(record, int(name.split("_")[-1]))
    raw = record.get(name)
    return float(raw) if isinstance(raw, (int, float)) else None


CHECKPOINTS = (0, 10, 100, 1000, 5000)
METRICS = (
    "rss_before_burst_bytes", "working_set_rss_bytes", "rss_after_free_bytes",
    "allocation_elapsed_ns", "allocation_minor_faults", "free_elapsed_ns",
    "memory_action_elapsed_ns", "reallocation_elapsed_ns",
    "reallocation_minor_faults", "reallocation_working_set_rss_bytes",
) + tuple("rss_at_{}".format(offset) for offset in CHECKPOINTS) + \
    tuple("retained_fraction_{}".format(offset) for offset in CHECKPOINTS) + \
    tuple("returned_fraction_{}".format(offset) for offset in CHECKPOINTS)


def comparison(values, label, seed):
    result = {"comparison": label, **describe(values)}
    result["median_95pct_bootstrap_ci"] = bootstrap_median_ci(values, seed)
    return result


def summarize_block(plan, block_id, by_key):
    versions = plan["comparison_versions"]
    repetitions = []
    for repetition in range(1, 16):
        arms = {version: by_key.get((block_id, repetition, version)) for version in versions}
        if all(arms.values()):
            repetitions.append(arms)
    metrics = []
    for metric in METRICS:
        by_version = {}
        for version in versions:
            values = [value(arms[version], metric) for arms in repetitions]
            by_version[version] = describe([item for item in values if item is not None])
        paired = []
        for denominator, numerator in ((versions[0], versions[1]),
                                       (versions[0], versions[2]),
                                       (versions[1], versions[2])):
            ratios = []
            differences = []
            for arms in repetitions:
                left = value(arms[denominator], metric)
                right = value(arms[numerator], metric)
                if left is not None and right is not None:
                    differences.append(right - left)
                    if left != 0:
                        ratios.append(right / left)
            stem = "{}:{}:{}/{}".format(block_id, metric, numerator, denominator)
            paired.append({
                "denominator": denominator,
                "numerator": numerator,
                "ratio": comparison(ratios, "ratio", plan["randomization_seed"] + stable_seed(stem + ":ratio")),
                "difference": comparison(differences, "difference", plan["randomization_seed"] + stable_seed(stem + ":difference")),
            })
        metrics.append({"metric": metric, "by_version": by_version, "paired": paired})
    return {"block_id": block_id,
            "complete_matched_repetitions": len(repetitions),
            "metrics": metrics}


def mode_effects(plan, by_key):
    baseline = "memory-passive-default"
    effects = []
    metrics = tuple("returned_fraction_{}".format(offset) for offset in CHECKPOINTS) + (
        "reallocation_elapsed_ns", "reallocation_minor_faults")
    for block in plan["blocks"]:
        block_id = block["block_id"]
        if block_id == baseline:
            continue
        for version in plan["comparison_versions"]:
            for metric in metrics:
                ratios = []
                differences = []
                for repetition in range(1, 16):
                    control = by_key.get((baseline, repetition, version))
                    treatment = by_key.get((block_id, repetition, version))
                    if control is None or treatment is None:
                        continue
                    left, right = value(control, metric), value(treatment, metric)
                    if left is None or right is None:
                        continue
                    differences.append(right - left)
                    if left != 0:
                        ratios.append(right / left)
                stem = "mode:{}:{}:{}".format(block_id, version, metric)
                effects.append({
                    "baseline_block": baseline,
                    "treatment_block": block_id,
                    "allocator_version": version,
                    "metric": metric,
                    "ratio": comparison(ratios, "ratio", plan["randomization_seed"] + stable_seed(stem + ":ratio")),
                    "difference": comparison(differences, "difference", plan["randomization_seed"] + stable_seed(stem + ":difference")),
                })
    return effects


def main():
    plan_path, plan = RUNNER.BASE.active_plan()
    RUNNER.validate_plan(plan_path, plan)
    result_root = ROOT / "results" / "active" / plan["result_namespace"] / "measured"
    by_key = latest_valid(result_root / "raw", plan)
    blocks = [summarize_block(plan, block["block_id"], by_key) for block in plan["blocks"]]
    summary = {
        "comparison_id": plan["comparison_id"],
        "design_revision": plan["design_revision"],
        "comparison_versions": plan["comparison_versions"],
        "valid_unique_records": len(by_key),
        "complete_matched_repetitions": sum(block["complete_matched_repetitions"] for block in blocks),
        "execution_status": "Not executed" if not by_key else "Partial or complete; inspect block counts",
        "blocks": blocks,
        "mode_effects_vs_passive_default": mode_effects(plan, by_key),
    }
    output = result_root / "summary.json"
    RUNNER.BASE.atomic_json(output, summary)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
