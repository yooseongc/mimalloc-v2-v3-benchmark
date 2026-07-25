#!/usr/bin/env python3
"""Derive summaries without modifying immutable raw result records."""
import argparse, json, math, pathlib, statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser()
parser.add_argument("--plan", type=pathlib.Path,
                    help="optional frozen plan; restrict derived groups to its block IDs")
args = parser.parse_args()
candidate_blocks = None
if args.plan:
    plan = json.loads(args.plan.read_text())
    if plan.get("design_status") != "Frozen":
        raise SystemExit("refusing: analysis scope plan is not Frozen")
    candidate_blocks = set(item["block_id"] for item in plan["runs"])

def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower, upper = int(math.floor(index)), int(math.ceil(index))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

def describe(values):
    if not values:
        return {"count": 0}
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else None
    # Normal-approximation CI is explicitly labelled; raw repetitions remain
    # available for non-parametric follow-up analysis.
    ci_half = 1.96 * stdev / math.sqrt(len(values)) if stdev is not None else None
    return {
        "count": len(values), "median": statistics.median(values), "mean": mean,
        "stdev": stdev, "coefficient_of_variation": stdev / mean if stdev is not None and mean else None,
        "minimum": min(values), "maximum": max(values),
        "p25": percentile(values, .25), "p75": percentile(values, .75),
        "iqr": percentile(values, .75) - percentile(values, .25),
        "mean_95ci_normal": [mean - ci_half, mean + ci_half] if ci_half is not None else None,
    }

raw = [json.loads(path.read_text()) for path in (ROOT / "results/raw").glob("*.json")]
valid_rows = [row for row in raw if row.get("valid")]
unique, duplicates = {}, []
for row in sorted(valid_rows, key=lambda item: item.get("timestamp", 0)):
    key = (row.get("block_id"), row.get("allocator_library_path"), row.get("repetition"))
    if key in unique:
        duplicates.append(row.get("run_id"))
    else:
        unique[key] = row
valid_rows = list(unique.values())
scoped_rows = [row for row in valid_rows if candidate_blocks is None or row.get("block_id") in candidate_blocks]

groups = {}
for row in scoped_rows:
    key = tuple(row.get(k) for k in ("block_id", "scenario", "thread_count", "size_bytes", "size_profile", "batch_size", "free_order", "allocator_version"))
    groups.setdefault(key, []).append(row)

summary = []
for key, rows in sorted(groups.items(), key=str):
    throughput = [r["operation_count"] * 1e9 / r["elapsed_ns"] for r in rows if r.get("elapsed_ns")]
    elapsed = [r["elapsed_ns"] for r in rows if r.get("elapsed_ns")]
    summary.append({"key": key, "valid_repetitions": len(rows),
                    "throughput_ops_per_second": describe(throughput),
                    "elapsed_ns": describe(elapsed)})

# Pair versions by frozen block and repetition.  Existing legacy raw records
# without a matching pair are deliberately not used in a cross-version ratio.
paired = {}
for row in scoped_rows:
    paired.setdefault((row.get("block_id"), row.get("repetition")), {})[str(row.get("allocator_version"))] = row
ratios = []
for (block_id, repetition), row_by_version in sorted(paired.items()):
    v2 = next((row for version, row in row_by_version.items() if version.startswith("2")), None)
    v3 = next((row for version, row in row_by_version.items() if version.startswith("3")), None)
    if not v2 or not v3 or not v2.get("elapsed_ns") or not v3.get("elapsed_ns"):
        continue
    ratios.append({"block_id": block_id, "repetition": repetition,
                   "throughput_ratio_v3_over_v2": v2["elapsed_ns"] / v3["elapsed_ns"],
                   "elapsed_ratio_v3_over_v2": v3["elapsed_ns"] / v2["elapsed_ns"]})
ratio_groups = {}
for ratio in ratios:
    ratio_groups.setdefault(ratio["block_id"], []).append(ratio)
paired_summary = []
for block_id, rows in sorted(ratio_groups.items()):
    paired_summary.append({"block_id": block_id, "paired_repetitions": len(rows),
                           "throughput_ratio_v3_over_v2": describe([r["throughput_ratio_v3_over_v2"] for r in rows]),
                           "elapsed_ratio_v3_over_v2": describe([r["elapsed_ratio_v3_over_v2"] for r in rows])})

out = ROOT / "results/summaries/summary.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"raw_records": len(raw), "valid_records": len(valid_rows),
                           "scoped_valid_records": len(scoped_rows),
                           "analysis_scope": str(args.plan) if args.plan else "all-valid-records",
                           "duplicate_records_excluded": duplicates, "groups": summary,
                           "paired_v3_over_v2": paired_summary}, indent=2) + "\n")
