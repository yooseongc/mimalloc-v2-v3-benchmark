"""Pinned dev3 comparison; only active observation components are reused."""
import json, math, os, pathlib, random, select, subprocess, sys, time
import release_v361 as base
ROOT=base.ROOT
EXP=ROOT/'experiments/dev3-20261106-v1'
OUT=ROOT/'results/dev3-20261106-v1'
BUILD=ROOT/'build/dev3-20261106-v1'
life,con=base.life,base.con
life.EXP=EXP/'lifecycle'; life.RESULTS=OUT/'lifecycle'; life.BUILD=BUILD/'lifecycle'
con.EXP=EXP/'concurrent'; con.OUT=OUT/'concurrent'; con.BUILD=BUILD/'concurrent'
life.VERSIONS={'v3.6.1':('56dc5eb80145f9a3ba7ca23d47c6a248b9d8586c',30601),
 'dev3-d6716d33':('d6716d33671c2f621b87be3c7ac016c6ba6b3c94',30602)}
VERSIONS=list(life.VERSIONS); con.VERSIONS=VERSIONS
base.EXP=EXP; base.OUT=OUT; base.BUILD=BUILD
MIB=2**20
CELLS=[(s,128*MIB,p) for s in (64,1024,4096) for p in (1,2)]
THREADS=[(0,64)]+[(m,s) for m in (1,2) for s in (64,4096)]

def build():
    base.build()
    a=json.loads((life.EXP/'artifacts.json').read_text())
    args=['g++','-std=c++17','-O3','-DNDEBUG','-Wall','-Wextra','-Werror',
          '-fno-builtin-malloc','-fno-builtin-free',str(ROOT/'observation/thread_lifecycle.cpp'),
          '-pthread','-ldl','-o',str(BUILD/'thread_lifecycle')]
    subprocess.run(args,check=True)
    assembly=con.cmd(['objdump','-d','-C',str(BUILD/'thread_lifecycle')])
    assert all(x in assembly for x in ('<malloc@plt>','<free@plt>','<pthread_create@plt>'))
    a['binary']=dict(path=str(BUILD/'thread_lifecycle'),sha256=con.sha(BUILD/'thread_lifecycle'),command=args)
    a['source_sha256']=con.sha(ROOT/'observation/thread_lifecycle.cpp')
    con.save(EXP/'threads/artifacts.json',a)
    for v in VERSIONS:
        cache=a['libraries'][v]['cmake_cache']
        assert 'MI_SECURE:STRING=OFF' in cache
        if v.startswith('dev3'): assert 'MI_MTE:BOOL=OFF' in cache and 'MI_PAC:BOOL=OFF' in cache
    con.save(EXP/'environment-extra.json',dict(cgroup=con.cg(),rpm=con.cmd(['rpm','-qa']),
        numa=con.cmd(['numactl','--hardware']),source_checked_at=con.stamp()))

def thread_run(cfg):
    a=json.loads((EXP/'threads/artifacts.json').read_text()); lib=a['libraries'][cfg['version']]
    assert con.sha(lib['path'])==lib['sha256'] and con.sha(a['binary']['path'])==a['binary']['sha256']
    env={k:v for k,v in os.environ.items() if not k.startswith('MIMALLOC_') and k!='LD_PRELOAD'}
    env['LD_PRELOAD']=lib['path']
    args=[a['binary']['path']]+[str(cfg[k]) for k in ('mode','size','cycles')]
    p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,universal_newlines=True)
    r=dict(config=cfg,valid=False,timestamp=con.stamp(),command=args,cgroup_before=con.cg(),
           library_sha256=lib['sha256'],binary_sha256=a['binary']['sha256'],mimalloc_environment={})
    def response():
        if not select.select([p.stdout],[],[],120)[0]: raise RuntimeError('timeout')
        return json.loads(p.stdout.readline())
    try:
        ready=response();r['ready']=ready
        assert ready['version']==lib['mi_version'] and pathlib.Path(ready['library']).resolve()==pathlib.Path(lib['path']).resolve()
        loaded={x.split()[-1] for x in con.read('/proc/{}/maps'.format(p.pid)).splitlines() if 'libmimalloc' in x}
        assert loaded=={lib['path']}
        assert sorted(os.sched_getaffinity(p.pid))==[2]
        r['baseline']=con.memory(p.pid,True)
        p.stdin.write('g');p.stdin.flush();r['final']=response();r['done']=con.memory(p.pid,True)
        f=r['final']; n=cfg['cycles']*1024 if cfg['mode'] else 0
        assert f['allocations']==f['frees']==n and f['live_objects']==0 and f['cycles']==cfg['cycles']
        assert f['checksum']==(cfg['cycles']*sum(2*(i%251) for i in range(1024)) if cfg['mode'] else 0)
        time.sleep(.1); r['idle']=con.memory(p.pid,True)
        p.stdin.write('q');p.stdin.flush();assert p.wait(timeout=10)==0
        r['cgroup_after']=con.cg()
        assert con.throttle(r['cgroup_before'])==con.throttle(r['cgroup_after'])
        assert all(r[k]['VmSwap']==r[k]['Swap']==0 for k in ('baseline','done','idle'))
        r['valid']=True
    except Exception as e:
        r['error']=repr(e);p.kill();p.wait()
    finally:
        r['stderr']=p.stderr.read();r['exit_code']=p.returncode
        for s in (p.stdin,p.stdout,p.stderr):s.close()
    return r

def threads(stage,entries):
    for i,e in enumerate(entries):
        path=OUT/'threads'/stage/('{:03d}.json'.format(i))
        if path.exists():
            r=json.loads(path.read_text());assert r['valid'] and r['config']==e;continue
        r=thread_run(e);con.save(path,r);assert r['valid'],(str(path),r.get('error'),r['stderr'])
        print('threads',stage,i+1,len(entries),e,round(r['final']['elapsed_ns']/1e9,3),flush=True)

def tconfig(v,cell,n,rep=0): return dict(version=v,mode=cell[0],size=cell[1],cycles=n,rep=rep)

def freeze():
    assert not (EXP/'plan.json').exists()
    pilots=[json.loads(p.read_text()) for p in sorted((con.OUT/'pilot').glob('*.json'))]
    tp=[json.loads(p.read_text()) for p in sorted((OUT/'threads/pilot').glob('*.json'))]
    smoke=list(OUT.glob('*/smoke/*.json'))
    assert len(pilots)==12 and len(tp)==10 and len(smoke)==22
    assert all(r['valid'] for r in pilots+tp+[json.loads(p.read_text()) for p in smoke])
    rng=random.Random(20261106); measured=[]; ts=[]; flows=[]; collects=[]
    for cell in CELLS:
        rows=[r for r in pilots if tuple(r['config'][k] for k in ('size','cap','pairs'))==cell]
        rate=max(r['config']['objects']/(r['final']['elapsed_ns']/1e9) for r in rows)
        n=max(int(math.ceil(rate*5/512))*512,1024*MIB//cell[0])
        for rep in range(5):
            vs=VERSIONS[:];rng.shuffle(vs);measured.extend(base.config(v,cell,n,rep) for v in vs)
    for cell in THREADS:
        rows=[r for r in tp if (r['config']['mode'],r['config']['size'])==cell]
        rate=max(r['config']['cycles']/(r['final']['elapsed_ns']/1e9) for r in rows)
        n=min(20000,max(200,int(math.ceil(rate*3))))
        for rep in range(5):
            vs=VERSIONS[:];rng.shuffle(vs);ts.extend(tconfig(v,cell,n,rep) for v in vs)
    for rep in range(5):
        for mode in ('same','remote'):
            vs=VERSIONS[:];rng.shuffle(vs);flows.extend(dict(version=v,mode=mode,rep=rep) for v in vs)
    for mode in ('same','remote'):
        vs=VERSIONS[:];rng.shuffle(vs);collects.extend(dict(version=v,mode=mode,intervention='collect_force') for v in vs)
    files=['docs/dev3-20261106-plan.md','observation/dev3_20261106.py','observation/release_v361.py',
        'observation/run.py','observation/run_concurrent.py','observation/lifecycle.cpp','observation/concurrent.cpp',
        'observation/thread_lifecycle.cpp']
    files += [str(p.relative_to(ROOT)) for p in EXP.glob('*/artifacts.json')]
    files += [str(p.relative_to(ROOT)) for p in OUT.glob('*/pilot/*.json')]
    files += [str(p.relative_to(ROOT)) for p in smoke]
    con.save(EXP/'plan.json',dict(status='Frozen',frozen_at=con.stamp(),seed=20261106,
        hashes={p:con.sha(ROOT/p) for p in files},concurrent=measured,threads=ts,lifecycle=flows,collect=collects))
    print('Frozen: 60 concurrent + 20 lifecycle + 4 collect + 50 thread',flush=True)

def main():
    assert sorted(os.sched_getaffinity(0))==[0,2,4,6,8,10]
    action=sys.argv[1]
    if action=='build':build();return
    if action=='freeze':freeze();return
    if action=='smoke':
        base.lifecycle('smoke',[dict(version=v,mode=m) for v in VERSIONS for m in ('same','remote')],64,.05)
        os.sched_setaffinity(0,{10})
        con.execute('smoke',[base.config(v,(s,2*MIB,p),8*MIB//s) for s in (64,4096) for p in (1,2) for v in VERSIONS],.01,True)
        threads('smoke',[tconfig(v,c,5) for c in THREADS for v in VERSIONS])
    elif action=='pilot':
        os.sched_setaffinity(0,{10})
        con.execute('pilot',[base.config(v,c,1024*MIB//c[0]) for c in CELLS for v in VERSIONS],.01)
        threads('pilot',[tconfig(v,c,200) for c in THREADS for v in VERSIONS])
    elif action=='measured':
        plan=json.loads((EXP/'plan.json').read_text());assert plan['status']=='Frozen'
        for p,h in plan['hashes'].items():assert con.sha(ROOT/p)==h,p
        base.lifecycle('measured',plan['lifecycle'],32768,5)
        base.lifecycle('collect',plan['collect'],32768,5)
        os.sched_setaffinity(0,{10});con.execute('measured',plan['concurrent'],1)
        threads('measured',plan['threads'])
    else:raise ValueError(action)
if __name__=='__main__':main()
