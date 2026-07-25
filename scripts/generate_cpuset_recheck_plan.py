#!/usr/bin/env python3
"""Clone frozen plans into a CPU-controlled recheck revision without mutation."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPU_LIST = "0,2,4,6,8,10,12,14"
SOURCE_PLANS = [
    "execution-plan-full-core-r6.json",
    "execution-plan-tier2-r7.json",
    "execution-plan-purge-r8.json",
    "execution-plan-tier3-build-r10.json",
    "execution-plan-tier3-runtime-r11.json",
]
BENCHMARK_SHA = "46ac4545b6c8375e08ac4894c71032ca9ec55e6e31b454bfc61275595a957b39"
runs = []
for filename in SOURCE_PLANS:
    source = json.loads((ROOT / "manifests" / filename).read_text())
    for item in source["runs"]:
        clone = dict(item)
        clone["experiment_id"] = item["experiment_id"] + "-cpuset-r12"
        clone["block_id"] = item["block_id"] + "-cpuset-r12"
        clone["cpu_list"] = CPU_LIST
        clone["benchmark_sha256"] = BENCHMARK_SHA
        runs.append(clone)
plan = {"schema_version": 1, "design_status": "Frozen", "randomization_seed": 20260725, "runs": runs}
(ROOT / "manifests" / "execution-plan-cpuset-r12.json").write_text(json.dumps(plan, indent=2) + "\n")
