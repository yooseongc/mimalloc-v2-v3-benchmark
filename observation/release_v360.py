"""Four-version follow-up; reuse only active, question-focused observation code."""
import datetime
import importlib.util
import json
import math
import os
import pathlib
import random
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP = ROOT/'experiments/release-v360-v1'
OUT = ROOT/'results/release-v360-v1'
BUILD = ROOT/'build/release-v360-v1'
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
life = module('release_lifecycle', ROOT/'observation/run.py')
con = module('release_concurrent', ROOT/'observation/run_concurrent.py')
life.EXP = EXP/'lifecycle'; life.BUILD = BUILD/'lifecycle'; life.RESULTS = OUT/'lifecycle'
life.VERSIONS = dict(life.VERSIONS)
life.VERSIONS['v3.6.0'] = ('b18ab4eef383f655e760881b02eff8af02800879', 30600)
con.EXP = EXP/'concurrent'; con.BUILD = BUILD/'concurrent'; con.OUT = OUT/'concurrent'
con.VERSIONS = list(life.VERSIONS)
VERSIONS = con.VERSIONS
MIB = 2**20
CELLS = [(s,128*MIB,p) for s in (64,1024,4096) for p in (1,2)] + [(4096,512*MIB,2)]
def config(v, cell, n, rep=0):
    s,c,p = cell
    return dict(version=v, size=s, cap=c, pairs=p, objects=n, retained=False, rep=rep)
def build():
    assert not (EXP/'plan.json').exists()
    life.build()
    con.BUILD.mkdir(parents=True,exist_ok=True)
    a = json.loads((life.EXP/'artifacts.json').read_text())
    command = ['g++','-std=c++17','-O3','-DNDEBUG','-Wall','-Wextra','-Werror',
        '-fno-builtin-malloc','-fno-builtin-free',str(ROOT/'observation/concurrent.cpp'),
        '-pthread','-ldl','-o',str(con.BUILD/'concurrent')]
    subprocess.run(command,check=True)
    assembly = con.cmd(['objdump','-d','-C',str(con.BUILD/'concurrent')])
    assert all(x in assembly for x in ('<memset@plt>','<malloc@plt>','<free@plt>'))
    (con.BUILD/'assembly.txt').write_text(assembly)
    a['binary'] = dict(path=str(con.BUILD/'concurrent'),sha256=con.sha(con.BUILD/'concurrent'),command=command)
    a['source_sha256'] = con.sha(ROOT/'observation/concurrent.cpp')
    con.save(con.EXP/'artifacts.json',a)
def lifecycle(stage, entries, n, idle):
    os.sched_setaffinity(0,{6})
    for i,e in enumerate(entries):
        path = life.RESULTS/stage/('{:03d}.json'.format(i))
        if path.exists():
            r = json.loads(path.read_text()); assert r['valid'] and r['entry']==e
            continue
        r = life.run_one(e['version'],e['mode'],n,idle,True,e.get('intervention','none'))
        r['entry'] = e
        con.save(path,r)
        assert r['valid'], (str(path),r.get('error'))
        print('lifecycle',stage,i+1,len(entries),e,flush=True)
def freeze():
    assert not (EXP/'plan.json').exists()
    pilots = [json.loads(p.read_text()) for p in sorted((con.OUT/'pilot').glob('*.json'))]
    assert len(pilots)==28 and all(r['valid'] for r in pilots)
    rng = random.Random(20261024); measured=[]; counts={}
    for cell in CELLS:
        rows = [r for r in pilots if (r['config']['size'],r['config']['cap'],r['config']['pairs'])==cell]
        rate = max(r['config']['objects']/(r['final']['elapsed_ns']/1e9) for r in rows)
        n = max(int(math.ceil(rate*3.5/512))*512, 1024*MIB//cell[0])
        counts[str(cell)] = n
        for rep in range(3):
            vs=VERSIONS[:];rng.shuffle(vs)
            measured.extend(config(v,cell,n,rep) for v in vs)
    flows=[]; collects=[]
    for rep in range(3):
        for mode in ('same','remote'):
            vs=VERSIONS[:];rng.shuffle(vs)
            flows.extend(dict(version=v,mode=mode,rep=rep) for v in vs)
    for mode in ('same','remote'):
        vs=VERSIONS[:];rng.shuffle(vs)
        collects.extend(dict(version=v,mode=mode,intervention='collect_force') for v in vs)
    files = ['docs/v360-plan.md','observation/release_v360.py','observation/run.py',
        'observation/run_concurrent.py','observation/lifecycle.cpp','observation/concurrent.cpp',
        'experiments/release-v360-v1/lifecycle/artifacts.json',
        'experiments/release-v360-v1/concurrent/artifacts.json']
    con.save(EXP/'plan.json',dict(status='Frozen',frozen_at=con.stamp(),seed=20261024,
        hashes={p:con.sha(ROOT/p) for p in files},counts=counts,concurrent=measured,lifecycle=flows,collect=collects))
    print('Frozen: 84 concurrent + 24 lifecycle + 8 collect',counts,flush=True)
def stats():
    a = json.loads((life.EXP/'artifacts.json').read_text())
    records=[]
    for v in ('v3.5.3','v3.6.0'):
        lib=a['libraries'][v]; assert con.sha(lib['path'])==lib['sha256']
        source=BUILD/('stats-'+v+'.cpp'); binary=BUILD/('stats-'+v)
        text=(ROOT/'observation/thread_stats_ab.cpp').read_text()
        text=text.replace('30503',str(lib['mi_version']))
        if v=='v3.6.0':
            text=text.replace('mi_option_collect_merges_stats','mi_option_stats_merge_on_collect')
            text=text.replace(r'\"purge_delay\":%ld',r'\"stats_merge_threshold_bytes\":%zu,\"purge_delay\":%ld')
            text=text.replace('API(mi_option_get)(mi_option_purge_delay));',
                'API(mi_option_get_size)(mi_option_stats_merge_threshold),API(mi_option_get)(mi_option_purge_delay));')
        source.write_text(text)
        command=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/('extern/mimalloc-'+v)/'include'),str(source),'-pthread','-ldl','-o',str(binary)]
        subprocess.run(command,check=True)
        for merge in (0,1):
            for size in (64,4096):
                for rep in range(2):
                    env={k:x for k,x in os.environ.items() if not k.startswith('MIMALLOC_') and k!='LD_PRELOAD'}
                    if v=='v3.6.0':
                        env['MIMALLOC_STATS_MERGE_ON_COLLECT']=str(merge)
                        if merge==0: env['MIMALLOC_STATS_MERGE_THRESHOLD']='0'
                    else: env['MIMALLOC_COLLECT_MERGES_STATS']=str(merge)
                    r=subprocess.run([str(binary),lib['path'],str(size)],env=env,
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=20)
                    path=EXP/'stats'/('{}-{}-{}-{}'.format(v,merge,size,rep))
                    path.parent.mkdir(parents=True,exist_ok=True)
                    pathlib.Path(str(path)+'.jsonl').write_text(r.stdout)
                    pathlib.Path(str(path)+'.stderr').write_text(r.stderr)
                    assert r.returncode==0,(v,r.stderr)
                    rows=[json.loads(s) for s in r.stdout.splitlines()]
                    assert rows[0]['collect_merges_stats']==merge
                    if v=='v3.6.0': assert rows[0]['stats_merge_threshold_bytes']==(0 if merge==0 else 524288)
                    for s in rows[1:]: assert s['A_free_calls']==s['B_alloc_calls']==0
                    f=rows[-1]
                    assert f['sum']['current_bytes']==0 and f['sum']['allocated_count']==1000
                    assert f['sum']['allocated_bytes']==size*1000
                    assert f['A_alloc_calls']==f['B_free_calls']==1000
                    records.append(dict(version=v,merge=merge,size=size,rep=rep,rows=rows,
                        source_sha256=con.sha(source),binary_sha256=con.sha(binary),command=command,valid=True))
                    print('stats',v,merge,size,rep,'PASS',flush=True)
    con.save(EXP/'stats/results.json',records)
def main():
    action=sys.argv[1]
    assert sorted(os.sched_getaffinity(0))==[0,2,4,6,8,10]
    if action=='build': build()
    elif action=='smoke':
        lifecycle('smoke',[dict(version=v,mode=m) for v in VERSIONS for m in ('same','remote')],64,.05)
        os.sched_setaffinity(0,{10})
        con.execute('smoke',[config(v,(s,2*MIB,p),8*MIB//s) for s in (64,4096) for p in (1,2) for v in VERSIONS],.01,True)
    elif action=='pilot':
        os.sched_setaffinity(0,{10})
        con.execute('pilot',[config(v,cell,1024*MIB//cell[0]) for cell in CELLS for v in VERSIONS],.01)
    elif action=='freeze': freeze()
    elif action=='measured':
        plan=json.loads((EXP/'plan.json').read_text())
        for p,h in plan['hashes'].items(): assert con.sha(ROOT/p)==h,p
        lifecycle('measured',plan['lifecycle'],32768,5)
        lifecycle('collect',plan['collect'],32768,5)
        os.sched_setaffinity(0,{10});con.execute('measured',plan['concurrent'],5)
    elif action=='stats': stats()
    else: raise ValueError(action)
if __name__=='__main__': main()
