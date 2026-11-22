"""One explicit owner-thread collection per condition, separately identified."""
import json
import os
import pathlib
import run

root=pathlib.Path(__file__).resolve().parents[1]
plan_path=root/'experiments/memory-behavior-v1/collect-plan.json'
plan=json.loads(plan_path.read_text())
assert plan['design_status']=='Frozen'
assert run.sha(root/'observation/run.py')==plan['runner_sha256']
assert run.sha(root/'observation/lifecycle.cpp')==plan['source_sha256']
assert run.sha(root/'experiments/memory-behavior-v1/artifacts.json')==plan['artifacts_sha256']
base=list((root/'results/memory-behavior-v1/measured').glob('*.json'))
assert len(base)==18 and all(json.loads(p.read_text())['valid'] for p in base)
os.sched_setaffinity(0,{6})
for i,item in enumerate(plan['execution_order']):
    destination=root/'results/memory-behavior-v1/collect-check'/('{:02d}.json'.format(i+1))
    if destination.exists():
        assert json.loads(destination.read_text())['valid']
        continue
    r=run.run_one(item['version'],item['mode'],32768,30,False,'collect_force')
    r.update(stage='collect-check',order=i+1,plan_sha256=run.sha(plan_path))
    run.save(destination,r)
    print('collect-check {}/6 {} {} valid={}'.format(i+1,item['version'],item['mode'],r['valid']),flush=True)
    assert r['valid'],r.get('error')
