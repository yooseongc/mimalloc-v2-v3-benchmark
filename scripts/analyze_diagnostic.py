#!/usr/bin/env python3
"""Summarize r19 diagnostic records without modifying raw data."""
import argparse
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
SYSCALLS = ("mmap", "munmap", "madvise", "brk")


def describe(values):
    return {
        "count": len(values),
        "median": statistics.median(values) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, default=ROOT / "results" / "raw" / "r19")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "results" / "summaries" / "diagnostic-r19.json")
    args = parser.parse_args()
    rows = []
    for path in sorted(args.input.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if row.get("valid"):
            rows.append(row)
    groups = {}
    for row in rows:
        key = (row.get("policy_label"), row.get("allocator_version"))
        groups.setdefault(key, []).append(row)
    summary = []
    for (policy, version), group in sorted(groups.items()):
        syscalls = {}
        for name in SYSCALLS:
            values = []
            for row in group:
                diagnostic = row.get("diagnostic", {}).get("strace", {})
                if diagnostic.get("available"):
                    values.append(diagnostic.get("counters", {}).get(name, {}).get("calls", 0))
            syscalls[name] = describe(values)
        def memory_value(section, name):
            values = []
            for row in group:
                maximum = row.get("diagnostic", {}).get("maximum_process_memory_bytes", {})
                value = maximum.get(section, {}).get(name)
                if value is not None:
                    values.append(value)
            return describe(values)
        summary.append({
            "policy_label": policy,
            "allocator_version": version,
            "valid_repetitions": len(group),
            "elapsed_ns": describe([row.get("elapsed_ns") for row in group if row.get("elapsed_ns")]),
            "page_faults_minor": describe([row.get("page_faults", {}).get("minor") for row in group if row.get("page_faults", {}).get("minor") is not None]),
            "syscall_calls": syscalls,
            "maximum_process_memory_bytes": {
                "AnonHugePages": memory_value("smaps_rollup", "AnonHugePages"),
                "Rss": memory_value("smaps_rollup", "Rss"),
                "VmRSS": memory_value("status", "VmRSS"),
                "VmHWM": memory_value("status", "VmHWM"),
            },
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"diagnostic": "r19", "valid_records": len(rows), "groups": summary}, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
