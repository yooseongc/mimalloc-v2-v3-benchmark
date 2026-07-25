#!/usr/bin/env python3
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
base = "/work"
sha = "46ac4545b6c8375e08ac4894c71032ca9ec55e6e31b454bfc61275595a957b39"
libsha = {"v2.1.2":"03a21de3a984a745c1bfe8ae6a6ad2ee79e4202c3364745ccba541e539c51f06","v3.4.3":"192b3a11694cbb86bbd54b5e2e63ed51942f16ad4a11e55fb0bd8fa2ad38bfb2"}
cells = [("lifetime-mix","lifetime_mix",200000000,64,1,"first-and-last",0), ("burst-purge","burst_purge",5000,65536,64,"per-page",1), ("thread-churn","thread_churn",50000,64,1,"first-and-last",0), ("large-alloc","large_alloc",70,64,1,"per-page",0)]
runs=[]
for version in ("v2.1.2","v3.4.3"):
 for name, scenario, ops, size, batch, touch, idle in cells:
  runs.append({"experiment_id":"tier2-"+name+"-r7","block_id":"tier2-"+name+"-r7","allocator_name":"mimalloc","allocator_version":version,"allocator_library_path":base+"/opt/mimalloc-"+version+"/release/lib64/libmimalloc.so","allocator_library_sha256":libsha[version],"benchmark_path":base+"/build/benchmark-release/benchmark/mimalloc-bench","benchmark_sha256":sha,"scenario":scenario,"thread_count":1,"size_bytes":size,"size_profile":"fixed","batch_size":batch,"free_order":"fifo","touch_mode":touch,"idle_ms":idle,"operation_count":ops,"warmup_count":0,"seed":20260725,"runtime_options":{},"thp_mode":"madvise","repetitions":15})
out=ROOT/"manifests/execution-plan-tier2-r7.json"
out.write_text(json.dumps({"schema_version":1,"design_status":"Frozen","randomization_seed":20260725,"runs":runs},indent=2)+"\n")
