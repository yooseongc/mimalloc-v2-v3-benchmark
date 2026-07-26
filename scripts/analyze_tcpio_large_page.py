#!/usr/bin/env python3
"""Analyze the r23 throughput and post-drain VmRSS A/B comparison."""
import argparse
import json
import pathlib
import random
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]


def bootstrap_ci(values, seed, iterations=10000):
    rng = random.Random(seed)
    medians = []
    for _ in range(iterations):
        sample = [values[rng.randrange(len(values))] for _ in values]
        medians.append(statistics.median(sample))
    medians.sort()
    return [medians[int(iterations * .025)], medians[int(iterations * .975)]]


def describe(values):
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "median": statistics.median(ordered),
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "mean": statistics.mean(ordered),
        "standard_deviation": statistics.stdev(ordered) if len(ordered) > 1 else 0,
    }


def rss_at(record, offset):
    samples = {row["offset_ms"]: row["vm_rss_bytes"]
               for row in record["post_drain_vm_rss"]}
    return samples[offset]


def half_release_ms(record):
    samples = record["post_drain_vm_rss"]
    initial, final = samples[0]["vm_rss_bytes"], samples[-1]["vm_rss_bytes"]
    if initial - final < 1024 * 1024:
        return None
    midpoint = final + (initial - final) / 2.0
    for row in samples:
        if row["vm_rss_bytes"] <= midpoint:
            return row["offset_ms"]
    return None


def measured(record):
    initial = rss_at(record, 0)
    final = rss_at(record, 5000)
    peak = record.get("peak_rss_bytes")
    return {
        "throughput_ops_per_second": (
            record["operation_count"] * 1e9 / record["elapsed_ns"]),
        "vm_rss_0ms_bytes": initial,
        "vm_rss_1000ms_bytes": rss_at(record, 1000),
        "vm_rss_5000ms_bytes": final,
        "peak_vm_rss_bytes": peak,
        "vm_rss_retained_0_over_peak": (
            initial / peak if peak not in (None, 0) else None),
        "vm_rss_immediate_release_fraction": (
            (peak - initial) / peak if peak not in (None, 0) else None),
        "vm_rss_retained_5000_over_0": final / initial if initial else None,
        "vm_rss_drop_5000_bytes": initial - final,
        "vm_rss_half_release_ms": half_release_ms(record),
        "peak_anon_huge_pages_bytes": record.get("peak_anon_huge_pages_bytes"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=pathlib.Path,
                        default=ROOT / "results/raw/r23")
    parser.add_argument("--design-revision", default="tcpio-large-page-v3")
    parser.add_argument("--output", type=pathlib.Path,
                        default=ROOT / "results/summaries/tcpio-large-page-r23.json")
    args = parser.parse_args()
    records = []
    for path in sorted(args.raw_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("design_revision") == args.design_revision
                and record.get("run_kind") == "final"):
            records.append(record)
    valid = [record for record in records if record.get("valid")]
    pairs = {}
    for record in valid:
        pairs.setdefault(record["repetition"], {})[record["allocator_version"]] = record
    pairs = {key: value for key, value in pairs.items()
             if set(value) == {"v2.1.2", "v3.4.3"}}
    if len(pairs) != 15:
        raise SystemExit("refusing: expected 15 complete valid pairs, got {}".format(len(pairs)))

    by_version = {"v2.1.2": [], "v3.4.3": []}
    ratios = {}
    half_time_ratios = []
    for repetition in sorted(pairs):
        v2 = measured(pairs[repetition]["v2.1.2"])
        v3 = measured(pairs[repetition]["v3.4.3"])
        by_version["v2.1.2"].append(v2)
        by_version["v3.4.3"].append(v3)
        for name in ("throughput_ops_per_second", "vm_rss_0ms_bytes",
                     "vm_rss_1000ms_bytes", "vm_rss_5000ms_bytes",
                     "peak_vm_rss_bytes", "vm_rss_retained_0_over_peak",
                     "vm_rss_retained_5000_over_0",
                     "peak_anon_huge_pages_bytes"):
            if v2[name] not in (None, 0) and v3[name] is not None:
                ratios.setdefault(name, []).append(v3[name] / v2[name])
        if (v2["vm_rss_half_release_ms"] not in (None, 0)
                and v3["vm_rss_half_release_ms"] is not None):
            half_time_ratios.append(
                v3["vm_rss_half_release_ms"] / v2["vm_rss_half_release_ms"])

    ratio_summary = {}
    for index, (name, values) in enumerate(sorted(ratios.items())):
        ratio_summary[name] = {
            "paired_count": len(values),
            "median_v3_over_v2": statistics.median(values),
            "paired_bootstrap_median_95ci": bootstrap_ci(values, 0x23B10C + index),
            "minimum": min(values),
            "maximum": max(values),
        }
    descriptive = {}
    for version, rows in by_version.items():
        descriptive[version] = {}
        for name in rows[0]:
            values = [row[name] for row in rows if row[name] is not None]
            if values:
                descriptive[version][name] = describe(values)

    throughput = ratio_summary["throughput_ops_per_second"]
    rss_1s = ratio_summary["vm_rss_1000ms_bytes"]
    rss_5s = ratio_summary["vm_rss_5000ms_bytes"]
    immediate_retained = ratio_summary["vm_rss_retained_0_over_peak"]
    throughput_clear = (
        throughput["median_v3_over_v2"] > 1
        and throughput["paired_bootstrap_median_95ci"][0] > 1)
    vmrss_no_worse = (
        rss_1s["median_v3_over_v2"] <= 1
        and rss_5s["median_v3_over_v2"] <= 1
        and immediate_retained["median_v3_over_v2"] <= 1)
    half_release = {
        "paired_count": len(half_time_ratios),
        "median_v3_over_v2": (
            statistics.median(half_time_ratios) if half_time_ratios else None),
    }
    if throughput_clear and vmrss_no_worse and (
            not half_time_ratios or half_release["median_v3_over_v2"] <= 1):
        decision = "v3 명료한 개선"
    elif throughput_clear and not vmrss_no_worse:
        decision = "처리량 개선이나 VmRSS trade-off"
    elif (throughput["median_v3_over_v2"] > 1 and vmrss_no_worse):
        decision = "v3 VmRSS 명확 개선, 처리량 우위 미확정"
    else:
        decision = "v3 명료한 개선 아님"
    summary = {
        "experiment_id": "r23",
        "design_revision": args.design_revision,
        "execution_status": "Executed",
        "condition": "THP=madvise; native large OS page request on; service-like/service",
        "final_record_count": len(records),
        "valid_record_count": len(valid),
        "invalid_record_count": len(records) - len(valid),
        "paired_count": len(pairs),
        "descriptive": descriptive,
        "paired_ratios": ratio_summary,
        "half_release_time": half_release,
        "throughput_clear_improvement": throughput_clear,
        "vmrss_no_worse": vmrss_no_worse,
        "decision": decision,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": decision,
        "throughput_ratio": throughput["median_v3_over_v2"],
        "rss_1s_ratio": rss_1s["median_v3_over_v2"],
        "rss_5s_ratio": rss_5s["median_v3_over_v2"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
