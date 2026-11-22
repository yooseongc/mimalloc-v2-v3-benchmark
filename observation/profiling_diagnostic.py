"""Bounded profiling follow-up using the unchanged active observation controller."""
import importlib.util
import json
import math
import os
import pathlib
import random
import shutil
import statistics
import subprocess
import sys
import time
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP = ROOT/'experiments/profiling-diagnostic-v1'
OUT = ROOT/'results/profiling-diagnostic-v1'
spec = importlib.util.spec_from_file_location('controller', str(ROOT/'observation/run_concurrent.py'))
con = importlib.util.module_from_spec(spec)
spec.loader.exec_module(con)
con.EXP = EXP
con.BUILD = ROOT/'build/release-v361-v1/concurrent'
VERSIONS = ['v3.6.0', 'v3.6.1']
MODES = ['off', 'sample512', 'sample4m', 'periodic512']

def run(stage, index, cfg, full=False):
    folder = OUT/stage/('{:03d}'.format(index))
    folder.mkdir(parents=True, exist_ok=False)
    env = {}
    mode = cfg['mode']
    if mode in MODES[1:]:
        env = dict(MIMALLOC_PROFILE=str(folder/'heap.text'),
                   MIMALLOC_PROFILE_SAMPLE_RATE='4MiB' if mode=='sample4m' else '512KiB',
                   MIMALLOC_PROFILE_ALLOC_INTERVAL='1GiB' if mode=='periodic512' else '0',
                   MIMALLOC_PROFILE_INUSE_INTERVAL='0', MIMALLOC_PROFILE_TIME_INTERVAL='0')
    if mode=='reclaim1': env['MIMALLOC_PAGE_RECLAIM_ON_FREE']='1'
    if mode=='stats512': env['MIMALLOC_STATS_MERGE_THRESHOLD']='512KiB'
    def popen(*args, **kw):
        kw['env'].update(env)
        return subprocess.Popen(*args, **kw)
    con.subprocess = types.SimpleNamespace(Popen=popen, PIPE=subprocess.PIPE)
    start=time.monotonic()
    r=con.run(cfg, idle=.1, full=full)
    r['controller_wall_seconds']=time.monotonic()-start
    r['mimalloc_environment']=env
    r['runtime_policy']='diagnostic '+mode
    profiles=[]
    for p in sorted(folder.glob('*.heap')):
        text=p.read_text()
        profiles.append(dict(path=str(p), sha256=con.sha(p), bytes=p.stat().st_size,
                             header=text.splitlines()[0]))
    r['profiles']=profiles
    if mode in MODES[1:] and not profiles:
        r['valid']=False; r['error']='no profile output'
    con.save(folder/'result.json', r)
    print(stage,index,cfg['version'],cfg['size'],mode,r['valid'],
          r.get('final',{}).get('elapsed_ns'),len(profiles),flush=True)
    assert r['valid'],r.get('error')
    return r

def config(v,s,mode,n,rep=0):
    return dict(version=v,size=s,mode=mode,objects=n,pairs=2,cap=128*2**20,retained=False,rep=rep)

def prepare():
    assert not EXP.exists()
    assert sorted(os.sched_getaffinity(0))==[0,2,4,6,8,10]
    artifact=json.loads((ROOT/'experiments/release-v361-v1/concurrent/artifacts.json').read_text())
    for v in VERSIONS:
        assert con.sha(artifact['libraries'][v]['path'])==artifact['libraries'][v]['sha256']
    assert con.sha(artifact['binary']['path'])==artifact['binary']['sha256']
    con.save(EXP/'artifacts.json',artifact)
    env=dict(kernel=con.cmd(['uname','-a']),cpu=con.cmd(['lscpu']),cgroup=con.cg(),
             thp=con.read('/sys/kernel/mm/transparent_hugepage/enabled'),
             meminfo=con.read('/proc/meminfo'),perf=shutil.which('perf'))
    if env['perf']:
        p=subprocess.run(['perf','stat','-e','cycles','true'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
        env['perf_probe']=dict(exit=p.returncode,stdout=p.stdout,stderr=p.stderr)
    con.save(EXP/'environment.json',env)
    os.sched_setaffinity(0,{10})
    i=0
    for v in VERSIONS:
        for s in (1024,4096):
            for mode in MODES:
                run('smoke',i,config(v,s,mode,256*2**20//s),True);i+=1
    pilots=[]
    for v in VERSIONS:
        for s in (1024,4096):
            pilots.append(run('pilot',len(pilots),config(v,s,'off',2**30//s)))
    counts={s:max(2**30//s,int(math.ceil(max(r['config']['objects']/(r['final']['elapsed_ns']/1e9) for r in pilots if r['config']['size']==s)*2/512))*512) for s in (1024,4096)}
    rng=random.Random(20261101); rows=[]
    for rep in range(3):
        block=[config(v,s,m,counts[s],rep) for v in VERSIONS for s in counts for m in MODES]
        block += [config('v3.6.1',s,m,counts[s],rep) for s in counts for m in ('reclaim1','stats512')]
        rng.shuffle(block);rows+=block
    files=['docs/profiling-diagnostic-plan.md','observation/profiling_diagnostic.py','observation/run_concurrent.py','observation/concurrent.cpp']
    con.save(EXP/'plan.json',dict(status='Frozen',frozen_at=con.stamp(),counts=counts,runs=rows,
             hashes={p:con.sha(ROOT/p) for p in files}))

def measured():
    plan=json.loads((EXP/'plan.json').read_text())
    for p,h in plan['hashes'].items(): assert con.sha(ROOT/p)==h
    os.sched_setaffinity(0,{10})
    for i,c in enumerate(plan['runs']):
        p=OUT/'measured'/('{:03d}'.format(i))/'result.json'
        if p.exists():
            r=json.loads(p.read_text()); assert r['valid'] and r['config']==c
        else: run('measured',i,c)

if __name__=='__main__':
    {'prepare':prepare,'measured':measured}[sys.argv[1]]()
