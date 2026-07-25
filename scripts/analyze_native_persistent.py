#!/usr/bin/env python3
"""Summarize paired r20 native-request performance records."""
import argparse
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]


def describe(values):
    return {"count": len(values), "median": statistics.median(values),
            "minimum": min(values), "maximum": max(values)} if values else {"count": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=pathlib.Path, default=ROOT / "manifests" / "execution-plan-native-persistent-r20.json")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "results" / "summaries" / "native-persistent-r20.json")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    blocks = {item["block_id"] for item in plan["runs"]}
    rows = []
    for path in (ROOT / "results" / "raw").glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if row.get("valid") and row.get("block_id") in blocks:
            rows.append(row)
    pairs = {}
    for row in rows:
        pairs.setdefault((row["block_id"], row["repetition"]), {})[str(row["allocator_version"])] = row
    groups = {}
    for (block, _), pair in pairs.items():
        v2 = next((row for version, row in pair.items() if version.startswith("2")), None)
        v3 = next((row for version, row in pair.items() if version.startswith("3")), None)
        if not v2 or not v3:
            continue
        groups.setdefault(block, []).append({
            "throughput_ratio_v3_over_v2": v2["elapsed_ns"] / v3["elapsed_ns"],
            "user_cpu_ratio_v3_over_v2": v3.get("user_cpu_ns", 0) / v2["user_cpu_ns"] if v2.get("user_cpu_ns") else None,
            "system_cpu_ratio_v3_over_v2": v3.get("system_cpu_ns", 0) / v2["system_cpu_ns"] if v2.get("system_cpu_ns") else None,
            "minor_fault_ratio_v3_over_v2": v3.get("page_faults", {}).get("minor", 0) / v2["page_faults"]["minor"] if v2.get("page_faults", {}).get("minor") else None,
            "rss_ratio_v3_over_v2": v3.get("peak_rss_bytes", 0) / v2["peak_rss_bytes"] if v2.get("peak_rss_bytes") else None,
        })
    output = []
    for block, values in sorted(groups.items()):
        output.append({"block_id": block, "paired_repetitions": len(values),
                       **{key: describe([value[key] for value in values if value[key] is not None])
                          for key in values[0]}})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"diagnostic": "r20", "paired_groups": output}, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
