#!/usr/bin/env python3
"""Freeze topology/stage operation counts from complete paired r22 pilots."""
import argparse
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=pathlib.Path, default=ROOT / "results/raw/r22")
    parser.add_argument("--output", type=pathlib.Path,
                        default=ROOT / "config/tcpio-r22-calibration.json")
    parser.add_argument("--target-seconds", type=float, default=20.0)
    parser.add_argument("--design-revision", required=True,
                        help="exact frozen revision; amendments are never pooled")
    args = parser.parse_args()
    if not 10 <= args.target_seconds <= 30:
        raise SystemExit("target seconds must remain within the frozen 10-30 second range")
    groups = {}
    for path in sorted(args.raw_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (record.get("experiment_id") != "r22" or record.get("run_kind") != "pilot"):
            continue
        if record.get("design_revision") != args.design_revision:
            continue
        if record.get("scenario") != "tcp_policy_record" or not record.get("valid"):
            continue
        key = "{}/{}".format(record["topology"], record["stage_work"])
        groups.setdefault(key, []).append(record)
    expected = {"isolated/allocator", "isolated/service",
                "service-like/allocator", "service-like/service"}
    if set(groups) != expected:
        raise SystemExit("refusing: all four topology/stage pilot groups are required")
    calibration = {}
    evidence = {}
    for key in sorted(expected):
        rows = groups[key]
        pairs = {(row["block_id"], row["repetition"]) for row in rows}
        if len(rows) < 12 or len(pairs) < 6:
            raise SystemExit("refusing: {} lacks three paired pilots in both policy arms".format(key))
        rates = [row["operation_count"] * 1e9 / row["elapsed_ns"] for row in rows]
        count = max(1, int(statistics.median(rates) * args.target_seconds))
        calibration[key] = count
        evidence[key] = {
            "valid_runs": len(rows),
            "median_operations_per_second": statistics.median(rates),
            "target_seconds": args.target_seconds,
            "frozen_operation_count": count,
        }
    document = {**calibration, "_evidence": evidence}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(calibration, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
