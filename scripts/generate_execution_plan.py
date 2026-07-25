#!/usr/bin/env python3
import argparse, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
p.add_argument("--output", type=pathlib.Path, required=True)
p.add_argument("--freeze", action="store_true")
args=p.parse_args()
if not args.freeze: raise SystemExit("refusing: pass --freeze only after pilot review")
base="/work"
library_sha256 = {"v2.1.2": "03a21de3a984a745c1bfe8ae6a6ad2ee79e4202c3364745ccba541e539c51f06", "v3.4.3": "192b3a11694cbb86bbd54b5e2e63ed51942f16ad4a11e55fb0bd8fa2ad38bfb2"}
benchmark_sha256 = "602863800c0b202366f8a837a8593afec359673f3d6f81241d91907b40b7b133"
runs=[]
local_variants = (
  ("fixed-small-allocate-free", "fixed", 1, "fifo"),
  ("fixed-small-batch-fifo", "fixed", 32, "fifo"),
  ("fixed-small-batch-lifo", "fixed", 32, "lifo"),
  ("fixed-small-batch-random", "fixed", 32, "random"),
)
for version in ("v2.1.2","v3.4.3"):
  for name, profile, batch_size, free_order in local_variants:
    runs.append({"experiment_id":"tier1-local-"+name+"-t1-r5","block_id":"tier1-local-"+name+"-t1-r5",
"allocator_name":"mimalloc","allocator_version":version,"allocator_library_path":base+"/opt/mimalloc-"+version+"/release/lib64/libmimalloc.so","allocator_library_sha256":library_sha256[version],"benchmark_path":base+"/build/benchmark-release/benchmark/mimalloc-bench","benchmark_sha256":benchmark_sha256,"scenario":"local_churn","thread_count":1,"size_bytes":64,"size_profile":profile,"batch_size":batch_size,"free_order":free_order,"touch_mode":"first-and-last","operation_count":200000000,"warmup_count":0,"seed":20260725,"runtime_options":{},"thp_mode":"madvise","repetitions":15})
  runs.append({"experiment_id":"tier1-remote-small-1x1-pinned-r5","block_id":"tier1-remote-small-1x1-pinned-r5",
"allocator_name":"mimalloc","allocator_version":version,"allocator_library_path":base+"/opt/mimalloc-"+version+"/release/lib64/libmimalloc.so","allocator_library_sha256":library_sha256[version],"benchmark_path":base+"/build/benchmark-release/benchmark/mimalloc-bench","benchmark_sha256":benchmark_sha256,"scenario":"remote_free","thread_count":2,"size_bytes":64,"touch_mode":"first-and-last","operation_count":125000000,"warmup_count":0,"seed":20260725,"runtime_options":{},"thp_mode":"madvise","repetitions":15})
args.output.write_text(json.dumps({"schema_version":1,"design_status":"Frozen","randomization_seed":20260725,"runs":runs},indent=2)+"\n")
