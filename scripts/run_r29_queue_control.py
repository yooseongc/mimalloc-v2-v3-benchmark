#!/usr/bin/env python3
"""Isolated pointer-transfer control; never subtract its timing from allocator runs."""
import json
import random
import run_comparison_r29 as R


def main():
    path, plan = R.BASE.active_plan()
    R.validate_plan(path, plan, "pilot")
    destination = R.ROOT / "results/active/r29-v353-v1/queue-control"
    with R.BASE.execution_lock(destination):
        digest = R.BASE.sha256_file(path)
        audit = R.BASE.preflight(plan, digest)
        if not audit["valid"]:
            raise SystemExit(json.dumps(audit))
        R.BASE.atomic_json(destination / "preflight.json", audit)
        entries = [item for item in R.entries_for(plan, {"core"}, "pilot")
                   if item["block_id"] == "core-remote-fixed-4x4"]
        random.Random(20260921).shuffle(entries)
        for item in entries:
            item.update(block_id="queue-only-4x4", scenario="queue_only", measurement_stage="queue-control")
        done, attempts = R.BASE.prior_state(destination / "raw")
        blocks = R.BASE.scheduled_blocks(entries, done, 20260921, 0)
        for block in blocks:
            for item in block:
                identity = R.BASE.run_identity(item)
                row = R.BASE.execute_one(item, attempts.get(identity, 0) + 1,
                                         destination / "raw", destination / "logs", digest)
                expected = item["operation_count"] * (item["operation_count"] + 1) // 2
                if not row["valid"] or row["checksum"] != expected:
                    raise SystemExit("queue-only control failed")
                print(json.dumps({"run_id": row["run_id"], "valid": row["valid"],
                                  "elapsed_s": row["elapsed_ns"] / 1e9}), flush=True)


if __name__ == "__main__":
    main()
