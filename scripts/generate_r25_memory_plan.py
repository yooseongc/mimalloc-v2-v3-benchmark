#!/usr/bin/env python3
import hashlib,json,pathlib
from generate_r24_plan import COMMITS,VERSIONS
ROOT=pathlib.Path(__file__).resolve().parents[1]; CPU="0,2,4,6,8,10,12,14"; SEED=20260825
def sha(p):
 d=hashlib.sha256(); d.update(p.read_bytes()); return d.hexdigest()
def main():
 bench=ROOT/"build/benchmark-release/benchmark/mimalloc-bench"; runs=[]
 for policy,env in (("upstream-default",{}),("purge-delay-1000",{"MIMALLOC_PURGE_DELAY":"1000"})):
  for idle in (0,10,100,1000,5000):
   block=f"r25-memory-{policy}-idle{idle}"
   for v in VERSIONS:
    lib=ROOT/f"opt/mimalloc-{v}/release/lib64/libmimalloc.so"
    runs.append({"experiment_id":block,"block_id":block,"profile":"memory-return","allocator_name":"mimalloc",
     "allocator_version":v,"allocator_commit":COMMITS[v],"allocator_library_path":f"/work/opt/mimalloc-{v}/release/lib64/libmimalloc.so",
     "allocator_library_sha256":sha(lib),"benchmark_path":"/work/build/benchmark-release/benchmark/mimalloc-bench","benchmark_sha256":sha(bench),
     "scenario":"burst_purge","thread_count":1,"size_bytes":65536,"size_profile":"fixed","batch_size":8192,
     "free_order":"fifo","touch_mode":"per-page","idle_ms":idle,"operation_count":1,"warmup_count":0,"seed":SEED,
     "runtime_options":env,"policy":policy,"thp_mode":"madvise","repetitions":15,"cpu_list":CPU,"design_revision":"r25-contract-v1"})
 plan={"schema_version":2,"comparison_id":"r25-memory-return","comparison_versions":list(VERSIONS),"design_status":"Frozen",
  "measurement_contract":"docs/r25-measurement-contract.md","randomization_seed":SEED,"runs":runs}
 out=ROOT/"manifests/execution-plan-r25-memory.json"; out.write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
