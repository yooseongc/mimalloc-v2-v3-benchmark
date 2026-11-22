#!/usr/bin/env python3
import hashlib,json,pathlib
from generate_r24_plan import COMMITS,VERSIONS
ROOT=pathlib.Path(__file__).resolve().parents[1]; SEED=20260825
def sha(p):
 d=hashlib.sha256(); d.update(p.read_bytes()); return d.hexdigest()
def main():
 source=json.loads((ROOT/"manifests/execution-plan-tcpio-r22e-final.json").read_text(encoding="utf-8"))
 wanted={"r22e-final-isolated-allocator-upstream-default","r22e-final-isolated-service-upstream-default"}
 templates={x["block_id"]:x for x in source["runs"] if x["block_id"] in wanted and x["allocator_version"]=="v2.1.2"}
 bench=ROOT/"build/benchmark-release/benchmark/mimalloc-bench"; runs=[]
 for old,t in sorted(templates.items()):
  block=old.replace("r22e-final","r25-latency")
  for v in VERSIONS:
   lib=ROOT/f"opt/mimalloc-{v}/release/lib64/libmimalloc.so"; x=dict(t)
   x.update({"block_id":block,"experiment_id":block,"profile":"latency","allocator_version":v,"allocator_commit":COMMITS[v],
    "allocator_library_path":f"/work/opt/mimalloc-{v}/release/lib64/libmimalloc.so","allocator_library_sha256":sha(lib),
    "benchmark_sha256":sha(bench),"repetitions":15,"seed":SEED,"post_drain_observe_ms":5000,"post_drain_sample_ms":100,
    "design_revision":"r25-contract-v1"}); runs.append(x)
 plan={"schema_version":2,"experiment_id":"r25-latency","comparison_id":"r25-latency","comparison_versions":list(VERSIONS),
  "design_status":"Frozen","design_revision":"r25-contract-v1","randomization_seed":SEED,"host_thp":"madvise","required_numa_balancing":"disabled-or-kernel-unsupported",
  "measurement_contract":"docs/r25-measurement-contract.md","runs":runs}
 (ROOT/"manifests/execution-plan-r25-latency.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
