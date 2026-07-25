#!/usr/bin/env python3
import json, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
base="/work"; sha="46ac4545b6c8375e08ac4894c71032ca9ec55e6e31b454bfc61275595a957b39"
lib={"v2.1.2":"03a21de3a984a745c1bfe8ae6a6ad2ee79e4202c3364745ccba541e539c51f06","v3.4.3":"192b3a11694cbb86bbd54b5e2e63ed51942f16ad4a11e55fb0bd8fa2ad38bfb2"}
runs=[]
for delay in ("0","1000","-1"):
 for version in ("v2.1.2","v3.4.3"):
  runs.append({"experiment_id":"tier2-purge-"+delay+"-r8","block_id":"tier2-purge-"+delay+"-r8","allocator_name":"mimalloc","allocator_version":version,"allocator_library_path":base+"/opt/mimalloc-"+version+"/release/lib64/libmimalloc.so","allocator_library_sha256":lib[version],"benchmark_path":base+"/build/benchmark-release/benchmark/mimalloc-bench","benchmark_sha256":sha,"scenario":"burst_purge","thread_count":1,"size_bytes":65536,"size_profile":"fixed","batch_size":64,"free_order":"fifo","touch_mode":"per-page","idle_ms":1,"operation_count":5000,"warmup_count":0,"seed":20260725,"runtime_options":{"MIMALLOC_PURGE_DELAY":delay},"thp_mode":"madvise","repetitions":15})
(ROOT/"manifests/execution-plan-purge-r8.json").write_text(json.dumps({"schema_version":1,"design_status":"Frozen","randomization_seed":20260725,"runs":runs},indent=2)+"\n")
