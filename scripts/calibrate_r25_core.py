#!/usr/bin/env python3
import argparse, json, pathlib, statistics
ROOT=pathlib.Path(__file__).resolve().parents[1]; EXPECTED={212,30403,30500}
def main():
 p=argparse.ArgumentParser(); p.add_argument("--plan",type=pathlib.Path,required=True); p.add_argument("--output",type=pathlib.Path,required=True); a=p.parse_args()
 plan=json.loads(a.plan.read_text(encoding="utf-8")); blocks={x["block_id"] for x in plan["runs"]}; rows=[]
 for f in (ROOT/"results/raw").glob("*.json"):
  r=json.loads(f.read_text(encoding="utf-8"))
  if r.get("block_id") in blocks and r.get("valid"): rows.append(r)
 cells=[]
 for b in sorted(blocks):
  selected=[r for r in rows if r["block_id"]==b]; matched={}
  for r in selected: matched.setdefault(r["repetition"],set()).add(int(r["allocator_version"]))
  if len(selected)!=9 or len(matched)!=3 or any(x!=EXPECTED for x in matched.values()): raise SystemExit("incomplete "+b)
  rates=[r["operation_count"]*1e9/r["elapsed_ns"] for r in selected]; elapsed=[r["elapsed_ns"]/1e9 for r in selected]; original=selected[0]["operation_count"]
  count=original if 10<=statistics.median(elapsed)<=30 else max(1000000,round(statistics.median(rates)*15/1000000)*1000000)
  cells.append({"name":b.removeprefix("r25-core-pilot-"),"valid_records":9,"matched_repetitions":3,"pilot_operation_count":original,
   "combined_median_elapsed_seconds":statistics.median(elapsed),"core_operation_count":count})
 result={"schema_version":2,"comparison_id":"r25-core","valid_pilot_records":len(rows),"cells":cells}
 a.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
