#!/usr/bin/env python3
"""Summarize r21 paired sampled-RSS records, ignoring post-exit empty samples."""
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]


def describe(values):
    return {"count": len(values), "median": statistics.median(values),
            "minimum": min(values), "maximum": max(values)} if values else {"count": 0}


def sample_values(row, section, key):
    return [sample.get(section, {}).get(key) for sample in row["diagnostic"].get("process_memory_samples", [])
            if sample.get(section, {}).get(key) is not None]


def metric(row, name):
    if name == "throughput_ops_per_second":
        return row["operation_count"] * 1e9 / row["elapsed_ns"]
    if name == "user_cpu_ns": return row.get("user_cpu_ns")
    if name == "system_cpu_ns": return row.get("system_cpu_ns")
    if name == "minor_faults": return row.get("page_faults", {}).get("minor")
    if name == "maximum_sampled_rss_bytes":
        values = sample_values(row, "smaps_rollup", "Rss")
        return max(values) if values else None
    if name == "last_sampled_rss_bytes":
        values = sample_values(row, "smaps_rollup", "Rss")
        return values[-1] if values else None
    if name == "maximum_anon_huge_pages_bytes":
        values = sample_values(row, "smaps_rollup", "AnonHugePages")
        return max(values) if values else None
    raise ValueError(name)


def main():
    input_dir = ROOT / "results" / "raw" / "r21"
    output = ROOT / "results" / "summaries" / "purge-matched-r21.json"
    rows = []
    for path in input_dir.glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("valid"):
            rows.append(row)
    names = ("throughput_ops_per_second", "user_cpu_ns", "system_cpu_ns", "minor_faults",
             "maximum_sampled_rss_bytes", "last_sampled_rss_bytes", "maximum_anon_huge_pages_bytes")
    by_version = {}
    for version in ("212", "30403"):
        group = [row for row in rows if str(row.get("allocator_version")) == version]
        by_version[version] = {name: describe([metric(row, name) for row in group if metric(row, name) is not None])
                               for name in names}
    pairs = {}
    for row in rows:
        pairs.setdefault(row["repetition"], {})[str(row["allocator_version"])] = row
    ratios = {}
    for name in names:
        values = []
        for pair in pairs.values():
            v2, v3 = pair.get("212"), pair.get("30403")
            if not v2 or not v3: continue
            denominator, numerator = metric(v2, name), metric(v3, name)
            if denominator not in (None, 0) and numerator is not None:
                values.append(numerator / denominator)
        ratios[name + "_ratio_v3_over_v2"] = describe(values)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"diagnostic": "r21", "valid_records": len(rows),
                                  "by_allocator_version": by_version, "paired_v3_over_v2": ratios}, indent=2) + "\n",
                      encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
