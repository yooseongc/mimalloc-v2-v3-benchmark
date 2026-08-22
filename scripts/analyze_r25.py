#!/usr/bin/env python3
import itertools,json,pathlib,statistics
ROOT=pathlib.Path(__file__).resolve().parents[1]; V=("v2.1.2","v3.4.3","v3.5.0")
def ver(r):
 value=r["allocator_version"]
 if isinstance(value,str) and value.startswith("v"): return value
 n=int(value); return {212:"v2.1.2",30403:"v3.4.3",30500:"v3.5.0"}[n]
def desc(x):
 return {"count":len(x),"median":statistics.median(x),"mean":statistics.mean(x),"stdev":statistics.stdev(x) if len(x)>1 else None,"minimum":min(x),"maximum":max(x)} if x else {"count":0}
def unique(rows):
 out={}
 for r in sorted(rows,key=lambda x:x.get("timestamp",0)):
  if r.get("valid"): out[(r["block_id"],r["repetition"],ver(r))]=r
 return list(out.values())
def summarize(rows,metrics):
 rows=unique(rows); by={}
 for r in rows: by.setdefault((r["block_id"],r["repetition"]),{})[ver(r)]=r
 ratios=[]
 for (block,rep), arms in by.items():
  if set(arms)!=set(V): continue
  for den,num in itertools.combinations(V,2):
   for name,fn in metrics.items():
    a,b=fn(arms[den]),fn(arms[num])
    if a not in (None,0) and b is not None: ratios.append((block,den,num,name,b/a))
 groups={}
 for block,den,num,name,value in ratios: groups.setdefault((block,den,num,name),[]).append(value)
 return {"valid_unique_records":len(rows),"ratios":[{"block_id":b,"denominator":d,"numerator":n,"metric":m,**desc(x)} for (b,d,n,m),x in sorted(groups.items())]}
def sample(r,section,key,mode="max"):
 x=[s.get(section,{}).get(key) for s in r.get("diagnostic",{}).get("process_memory_samples",[]) if s.get(section,{}).get(key) is not None]
 return (max(x) if mode=="max" else x[-1]) if x else None
def rss_at(r,offset):
 x={s["offset_ms"]:s["vm_rss_bytes"] for s in r.get("post_drain_vm_rss",[])}; return x.get(offset)
def main():
 core=[json.loads(p.read_text()) for p in (ROOT/"results/raw").glob("*.json") if json.loads(p.read_text()).get("block_id","").startswith("r25-core-core-")]
 mem=[json.loads(p.read_text()) for p in (ROOT/"results/raw/r25-memory").glob("*.json")]
 lat=[json.loads(p.read_text()) for p in (ROOT/"results/raw/r25-latency").glob("*.json")]
 result={"schema_version":2,"comparison_versions":V,
  "core":summarize(core,{"throughput":lambda r:r["operation_count"]*1e9/r["elapsed_ns"],"elapsed_ns":lambda r:r["elapsed_ns"],"rss":lambda r:r.get("peak_rss_bytes")}),
  "memory_return":summarize(mem,{"rss_after_free":lambda r:r.get("rss_after_free_bytes"),"rss_after_idle":lambda r:r.get("rss_after_idle_bytes"),"max_sampled_rss":lambda r:sample(r,"smaps_rollup","Rss"),"last_sampled_rss":lambda r:sample(r,"smaps_rollup","Rss","last"),"max_pss":lambda r:sample(r,"smaps_rollup","Pss"),"max_anon_huge":lambda r:sample(r,"smaps_rollup","AnonHugePages")}),
  "latency":summarize(lat,{"throughput":lambda r:r.get("operations_per_second"),"p99_ns":lambda r:r.get("latency_percentiles_ns",{}).get("p99"),"p99_9_ns":lambda r:r.get("latency_percentiles_ns",{}).get("p99_9"),"rss_0ms":lambda r:rss_at(r,0),"rss_5000ms":lambda r:rss_at(r,5000)})}
 out=ROOT/"results/summaries/summary-r25.json"; out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8"); print(out)
if __name__=="__main__": main()
