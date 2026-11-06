#!/usr/bin/env python3
"""Materialize a draft r29 plan from historical workload definitions and real artifacts."""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT / "experiments/r29-v353-v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (DEST / "plan.json").exists():
        raise SystemExit("refusing to overwrite an existing plan")
    r27 = json.loads((ROOT / "experiments/r27-dev3-snapshot-v1/plan.json").read_text())
    r28 = json.loads((ROOT / "experiments/r28-memory-return-v1/plan.json").read_text())
    plan = r27
    plan.update(comparison_id="r29-v353-v1", comparison_versions=["v2.1.2", "v3.5.0", "v3.5.3"],
                design_status="Draft", design_revision="r29-v353-v1", result_namespace="r29-v353-v1",
                contract_path="experiments/r29-v353-v1/contract.md",
                contract_sha256=sha(DEST / "contract.md"), randomization_seed=20260921)
    plan["runner"] = {"path": "scripts/run_comparison_r29.py", "sha256": sha(ROOT / "scripts/run_comparison_r29.py"),
                      "dependencies": [{"path": path, "sha256": sha(ROOT / path)} for path in
                                       ("scripts/run_active_benchmark.py", "scripts/run_memory_return_r28.py")]}
    plan["benchmark"] = r28["benchmark"]
    plan["environment"]["timeout_seconds"] = 180
    plan["block_defaults"]["seed"] = 20260921
    plan["blocks"] = [b for b in plan["blocks"] if b["profile"] != "memory-return"]
    for block in r28["blocks"]:
        plan["blocks"].append(dict(r28["block_defaults"], **block))
    plan["allocators"] = plan["allocators"][:2] + [{
        "version": "v3.5.3", "commit": "d4881d338125e1cb7c47ba4cfb398d6f7c0c8d45", "mi_version": 30503,
        "library_path": "/work/opt/mimalloc-v3.5.3/release/lib64/libmimalloc.so",
        "library_sha256": sha(ROOT / "opt/mimalloc-v3.5.3/release/lib64/libmimalloc.so.3.5")}]
    (DEST / "plan.json").write_bytes((json.dumps(plan, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
