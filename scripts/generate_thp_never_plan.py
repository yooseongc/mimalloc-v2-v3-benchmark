#!/usr/bin/env python3
import json, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
source=json.loads((ROOT/"manifests/execution-plan-tier2-r7.json").read_text())
for item in source["runs"]:
    item["experiment_id"]=item["experiment_id"].replace("-r7","-thp-never-r9")
    item["block_id"]=item["block_id"].replace("-r7","-thp-never-r9")
    item["thp_mode"]="never"
(ROOT/"manifests/execution-plan-tier2-thp-never-r9.json").write_text(json.dumps(source,indent=2)+"\n")
