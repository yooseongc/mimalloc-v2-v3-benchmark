"""Separate within-version one-option control; never changes primary artifacts."""
import importlib.util
import json
import os
import pathlib
import random
import subprocess

root=pathlib.Path('/work')
build=root/'build/release-v360-v1/reclaim-control'
exp=root/'experiments/release-v360-v1/reclaim-control'
out=root/'results/release-v360-v1/reclaim-control'
build.mkdir(parents=True,exist_ok=True);exp.mkdir(parents=True,exist_ok=True)
base=(root/'observation/run_concurrent.py').read_text()
needle="    env['LD_PRELOAD'] = lib['path']"
assert base.count(needle)==1
base=base.replace(needle,needle+"\n    env['MIMALLOC_PAGE_RECLAIM_ON_FREE'] = str(cfg['reclaim'])")
path=build/'controller.py';path.write_text(base)
spec=importlib.util.spec_from_file_location('reclaim_controller',str(path))
con=importlib.util.module_from_spec(spec);spec.loader.exec_module(con)
artifact=json.loads((root/'experiments/release-v360-v1/concurrent/artifacts.json').read_text())
plan=json.loads((root/'experiments/release-v360-v1/plan.json').read_text())
source=(root/'observation/concurrent.cpp').read_text()
source='#include "mimalloc.h"\n'+source
source=source.replace(r'\"live_bytes\":%zu}',r'\"live_bytes\":%zu,\"page_reclaim_on_free\":%ld}',1)
needle='getpid(),ver(),a.dli_fname,cap);'
assert source.count(needle)==1
source=source.replace(needle,'getpid(),ver(),a.dli_fname,cap,reinterpret_cast<decltype(&mi_option_get)>(dlsym(RTLD_DEFAULT,"mi_option_get"))(mi_option_page_reclaim_on_free));')
cpp=build/'concurrent.cpp';cpp.write_text(source)
for v in ('v3.5.3','v3.6.0'):
    directory=build/v;directory.mkdir(parents=True,exist_ok=True)
    cmd=['g++','-std=c++17','-O3','-DNDEBUG','-Wall','-Wextra','-Werror','-fno-builtin-malloc','-fno-builtin-free',
        '-I'+str(root/('extern/mimalloc-'+v)/'include'),str(cpp),'-pthread','-ldl','-o',str(directory/'concurrent')]
    subprocess.run(cmd,check=True)
    a=dict(artifact)
    a['binary']=dict(path=str(directory/'concurrent'),sha256=con.sha(directory/'concurrent'),command=cmd)
    a['source_sha256']=con.sha(cpp)
    con.save(exp/v/'artifacts.json',a)
rng=random.Random(2026102401);order=[]
for size in (1024,4096):
    n=next(c['objects'] for c in plan['concurrent'] if c['size']==size and c['pairs']==2 and c['cap']==128*2**20)
    for rep in range(3):
        cells=[dict(version=v,reclaim=r,rep=rep,size=size,pairs=2,cap=128*2**20,objects=n,retained=False)
               for v in ('v3.5.3','v3.6.0') for r in (0,1)]
        rng.shuffle(cells);order.extend(cells)
con.save(exp/'plan.json',dict(status='Frozen',frozen_at=con.stamp(),order=order,
    design_sha256=con.sha(exp/'design.md'),runner_sha256=con.sha(__file__),controller_sha256=con.sha(path),
    source_sha256=con.sha(cpp),primary_plan_sha256=con.sha(root/'experiments/release-v360-v1/plan.json')))
os.sched_setaffinity(0,{10})
for i,c in enumerate(order):
    con.EXP=exp/c['version'];con.BUILD=build/c['version']
    p=out/('{:03d}.json'.format(i))
    assert not p.exists(),'Do not overwrite control observations'
    r=con.run(c,.1,False)
    r['runtime_policy']='explicit-page-reclaim-on-free'
    r['mimalloc_environment']={'MIMALLOC_PAGE_RECLAIM_ON_FREE':str(c['reclaim'])}
    con.save(p,r)
    assert r['valid'],(p,r.get('error'))
    assert r['ready']['page_reclaim_on_free']==c['reclaim']
    print('reclaim',i+1,len(order),c['version'],c['size'],c['reclaim'],round(r['final']['elapsed_ns']/1e9,3),flush=True)
