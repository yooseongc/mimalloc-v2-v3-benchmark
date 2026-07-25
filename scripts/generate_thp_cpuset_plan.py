#!/usr/bin/env python3
"""Freeze the CPU-controlled THP=never recheck plan."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = json.loads((ROOT / "manifests" / "execution-plan-tier2-thp-never-r9.json").read_text())
for item in source["runs"]:
    item["experiment_id"] += "-cpuset-r13"
    item["block_id"] += "-cpuset-r13"
    item["cpu_list"] = "0,2,4,6,8,10,12,14"
    item["benchmark_sha256"] = "46ac4545b6c8375e08ac4894c71032ca9ec55e6e31b454bfc61275595a957b39"
source["randomization_seed"] = 20260725
(ROOT / "manifests" / "execution-plan-tier2-thp-never-cpuset-r13.json").write_text(json.dumps(source, indent=2) + "\n")
