"""Equal purge delay and arena multiplier, common workload binary for all four versions."""
import importlib.util
import json
import os
import pathlib
import random
import subprocess
import sys

ROOT=pathlib.Path('/work')
EXP=ROOT/'experiments/purge-delay-v1'
BUILD=ROOT/'build/purge-delay-v1'
OUT=ROOT/'results/purge-delay-v1'
VERSIONS=['v2.1.2','v3.5.0','v3.5.3','v3.6.0']
def load(p):return json.loads(p.read_text())
def module(p):
    s=importlib.util.spec_from_file_location('purge_controller',str(p))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    return m
def controller():
    con=module(BUILD/'controller.py');con.EXP=EXP;con.BUILD=BUILD
    return con
def prepare():
    assert not (EXP/'plan.json').exists(),'already frozen'
    BUILD.mkdir(parents=True,exist_ok=True);EXP.mkdir(parents=True,exist_ok=True)
    base=(ROOT/'observation/run_concurrent.py').read_text()
    needle="    env['LD_PRELOAD'] = lib['path']"
    assert base.count(needle)==1
    base=base.replace(needle,needle+"\n    if cfg['delay'] is not None:\n        env['MIMALLOC_PURGE_DELAY']=str(cfg['delay'])\n        env['MIMALLOC_ARENA_PURGE_MULT']='1'")
    needle="        assert r['version']==lib['mi_version'] and r['live_bytes']==cfg['cap']"
    assert base.count(needle)==1
    base=base.replace(needle,needle+"\n        assert r['purge_delay']==(cfg['delay'] if cfg['delay'] is not None else (10 if cfg['version']=='v2.1.2' else 1000))\n        assert r['arena_purge_mult']==(1 if cfg['delay'] is not None else (10 if cfg['version']=='v2.1.2' else 4))\n        assert r['purge_decommits']==1")
    (BUILD/'controller.py').write_text(base)
    con=controller()
    a=load(ROOT/'experiments/release-v360-v1/concurrent/artifacts.json')
    enum_source=BUILD/'enum.cpp'
    enum_source.write_text('#include "mimalloc.h"\n#include <cstdio>\nint main(){std::printf("%d %d %d",int(mi_option_purge_delay),int(mi_option_arena_purge_mult),int(mi_option_purge_decommits));}\n')
    ids={};enum_commands={}
    for v in VERSIONS:
        lib=a['libraries'][v];assert con.sha(lib['path'])==lib['sha256']
        src=ROOT/('extern/mimalloc-'+v)
        git=['git','-c','safe.directory='+str(src),'-C',str(src)]
        assert con.cmd(git+['rev-parse','HEAD'])==lib['commit']
        assert not con.cmd(git+['status','--porcelain','--untracked-files=no'])
        cmd=['g++','-std=c++17','-I'+str(src/'include'),str(enum_source),'-o',str(BUILD/'enum')]
        subprocess.run(cmd,check=True);enum_commands[v]=cmd
        ids[v]=[int(x) for x in con.cmd([str(BUILD/'enum')]).split()]
    # Only option lookup IDs vary; all versions execute the same workload binary.
    lookup='\nstatic long option_value(int version,int slot) {\n  const int* ids=nullptr;\n'
    for v in VERSIONS:
        vals=','.join(str(x) for x in ids[v]);num=a['libraries'][v]['mi_version']
        lookup+='  static const int ids_{}[]={{ {} }}; if(version=={})ids=ids_{};\n'.format(num,vals,num,num)
    lookup+='  auto get=reinterpret_cast<long(*)(int)>(dlsym(RTLD_DEFAULT,"mi_option_get"));\n  if(!get||!ids) { std::abort(); }\n  return get(ids[slot]);\n}\n'
    source=(ROOT/'observation/concurrent.cpp').read_text()
    source=source.replace('constexpr size_t batch=256;',lookup+'\nconstexpr size_t batch=256;')
    source=source.replace(r'\"live_bytes\":%zu}',r'\"live_bytes\":%zu,\"purge_delay\":%ld,\"arena_purge_mult\":%ld,\"purge_decommits\":%ld}',1)
    source=source.replace('getpid(),ver(),a.dli_fname,cap);','getpid(),ver(),a.dli_fname,cap,option_value(ver(),0),option_value(ver(),1),option_value(ver(),2));')
    cpp=BUILD/'concurrent.cpp';cpp.write_text(source)
    cmd=['g++','-std=c++17','-O3','-DNDEBUG','-Wall','-Wextra','-Werror','-fno-builtin-malloc','-fno-builtin-free',str(cpp),'-pthread','-ldl','-o',str(BUILD/'concurrent')]
    subprocess.run(cmd,check=True)
    a['binary']=dict(path=str(BUILD/'concurrent'),sha256=con.sha(BUILD/'concurrent'),command=cmd)
    a['source_sha256']=con.sha(cpp);a['enum_ids']=ids;a['enum_commands']=enum_commands
    a['parent_artifacts_sha256']=con.sha(ROOT/'experiments/release-v360-v1/concurrent/artifacts.json')
    a['environment_current']=dict(kernel=con.cmd(['uname','-a']),cpu=con.cmd(['lscpu']),
        thp=con.read('/sys/kernel/mm/transparent_hugepage/enabled'),cgroup=con.cg(),allowed_cpus=sorted(os.sched_getaffinity(0)))
    con.save(EXP/'artifacts.json',a)
    old=load(ROOT/'experiments/release-v360-v1/plan.json')
    n=next(c['objects'] for c in old['concurrent'] if c['size']==1024 and c['pairs']==2 and c['cap']==128*2**20)
    rng=random.Random(2026102402);order=[]
    for rep in range(3):
        block=[config(v,d,n,128*2**20,rep) for v in VERSIONS for d in (10,1000)]
        rng.shuffle(block);order.extend(block)
    files=['docs/purge-delay-plan.md','observation/purge_delay.py','observation/run_concurrent.py','observation/concurrent.cpp']
    con.save(EXP/'plan.json',dict(status='Frozen',frozen_at=con.stamp(),order=order,seed=2026102402,
        hashes={p:con.sha(ROOT/p) for p in files},artifacts_sha256=con.sha(EXP/'artifacts.json'),
        generated_controller_sha256=con.sha(BUILD/'controller.py'),generated_source_sha256=con.sha(cpp)))
    print('Prepared common binary; option IDs:',ids,flush=True)
def config(v,d,n,cap,rep=0):
    return dict(version=v,delay=d,size=1024,pairs=2,cap=cap,objects=n,retained=False,rep=rep)
def execute(stage,configs,idle,full=False):
    con=controller();plan=load(EXP/'plan.json')
    for p,h in plan['hashes'].items():assert con.sha(ROOT/p)==h,p
    assert con.sha(EXP/'artifacts.json')==plan['artifacts_sha256']
    assert con.sha(BUILD/'controller.py')==plan['generated_controller_sha256']
    assert con.sha(BUILD/'concurrent.cpp')==plan['generated_source_sha256']
    os.sched_setaffinity(0,{10})
    for i,c in enumerate(configs):
        p=OUT/stage/('{:03d}.json'.format(i))
        if p.exists():
            old=load(p);assert old['config']==c and old['valid'];continue
        r=con.run(c,idle,full)
        r['runtime_policy']='explicit-delay-and-arena-multiplier' if c['delay'] is not None else 'upstream-default'
        r['mimalloc_environment']={} if c['delay'] is None else {'MIMALLOC_PURGE_DELAY':str(c['delay']),'MIMALLOC_ARENA_PURGE_MULT':'1'}
        r['plan_sha256']=con.sha(EXP/'plan.json')
        con.save(p,r)
        assert r['valid'],(str(p),r.get('error'),r.get('stderr'))
        print(stage,i+1,len(configs),c['version'],'delay',r['ready']['purge_delay'],'mult',r['ready']['arena_purge_mult'],
              'seconds',round(r['final']['elapsed_ns']/1e9,3),'idle RSS MiB',round(r['checkpoints'][-1]['Rss']/2**20,2),flush=True)
def main():
    assert sorted(os.sched_getaffinity(0))==[0,2,4,6,8,10]
    action=sys.argv[1]
    if action=='prepare':prepare()
    elif action=='smoke':
        execute('defaults',[config(v,None,8192,2*2**20) for v in VERSIONS],.01,True)
        execute('smoke',[config(v,d,8192,2*2**20) for v in VERSIONS for d in (10,1000)],.01,True)
    elif action=='measured':execute('measured',load(EXP/'plan.json')['order'],5)
    else:raise ValueError(action)
if __name__=='__main__':main()
