#!/usr/bin/env python3
"""Generate r27 by reusing only the frozen r26 workload definitions."""
import copy
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments" / "r26-baseline-v1" / "plan.json"
CONTRACT = ROOT / "experiments" / "r27-dev3-snapshot-v1" / "contract.md"
OUTPUT = ROOT / "experiments" / "r27-dev3-snapshot-v1" / "plan.json"
RUNNER = ROOT / "scripts" / "run_active_benchmark.py"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    plan = copy.deepcopy(json.loads(BASE.read_text(encoding="utf-8")))
    plan.update({
        "comparison_id": "r27-dev3-snapshot-v1",
        "comparison_versions": ["v2.1.2", "v3.5.0", "dev3-622d421f"],
        "design_status": "Frozen",
        "design_revision": "r27-dev3-snapshot-v1",
        "contract_path": "experiments/r27-dev3-snapshot-v1/contract.md",
        "contract_sha256": sha256(CONTRACT),
        "result_namespace": "r27-dev3-snapshot-v1",
        "randomization_seed": 20260827,
        "runner": {"path": "scripts/run_active_benchmark.py", "sha256": sha256(RUNNER)},
    })
    by_version = {item["version"]: item for item in plan["allocators"]}
    plan["allocators"] = [
        by_version["v2.1.2"],
        by_version["v3.5.0"],
        {
            "version": "dev3-622d421f",
            "commit": "622d421f647fc41a2dfe90bc45174770129d78b4",
            "mi_version": 30500,
            "library_path": "/work/opt/mimalloc-dev3-622d421f/release/lib64/libmimalloc.so",
            "library_sha256": "49a1be072b80b98fced4135ae5d835a5fe8576648ca2949a8b9a6a70acdba95d",
        },
    ]
    plan["block_defaults"]["seed"] = 20260827
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
