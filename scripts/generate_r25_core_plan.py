#!/usr/bin/env python3
"""Generate frozen r25 Core smoke/pilot or calibrated core plans."""
import argparse, hashlib, json, pathlib
from generate_r24_plan import CELLS, COMMITS, VERSIONS

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEED, CPU_LIST = 20260825, "0,2,4,6,8,10,12,14"

def sha(path):
    d = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""): d.update(chunk)
    return d.hexdigest()

def main():
    p = argparse.ArgumentParser(); p.add_argument("--stage", choices=("smoke","pilot","core"), required=True)
    p.add_argument("--output", type=pathlib.Path, required=True); p.add_argument("--calibration", type=pathlib.Path)
    a = p.parse_args(); benchmark = ROOT / "build/benchmark-release/benchmark/mimalloc-bench"
    libs = {v: ROOT / f"opt/mimalloc-{v}/release/lib64/libmimalloc.so" for v in VERSIONS}
    counts = {}
    if a.stage == "core":
        if not a.calibration: raise SystemExit("core requires --calibration")
        c = json.loads(a.calibration.read_text(encoding="utf-8"))
        if c.get("comparison_id") != "r25-core" or c.get("valid_pilot_records") != 45: raise SystemExit("bad calibration")
        counts = {x["name"]: x["core_operation_count"] for x in c["cells"]}
    reps = {"smoke":1,"pilot":3,"core":15}[a.stage]; runs=[]
    for cell in CELLS:
        ops = min(cell["operation_count"],100000) if a.stage=="smoke" else counts.get(cell["name"],cell["operation_count"])
        block=f"r25-core-{a.stage}-{cell['name']}"
        for v in VERSIONS:
            runs.append({"experiment_id":block,"block_id":block,"profile":"core","allocator_name":"mimalloc",
              "allocator_version":v,"allocator_commit":COMMITS[v],"allocator_library_path":f"/work/opt/mimalloc-{v}/release/lib64/libmimalloc.so",
              "allocator_library_sha256":sha(libs[v]),"benchmark_path":"/work/build/benchmark-release/benchmark/mimalloc-bench",
              "benchmark_sha256":sha(benchmark),**{k:x for k,x in cell.items() if k!="name"},"operation_count":ops,
              "warmup_count":0,"seed":SEED,"runtime_options":{},"policy":"upstream-default","thp_mode":"madvise",
              "repetitions":reps,"cpu_list":CPU_LIST,"design_revision":"r25-contract-v1"})
    plan={"schema_version":2,"comparison_id":"r25-core","comparison_versions":list(VERSIONS),"design_status":"Frozen",
          "measurement_contract":"docs/r25-measurement-contract.md","randomization_seed":SEED,"runs":runs}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
if __name__ == "__main__": main()
