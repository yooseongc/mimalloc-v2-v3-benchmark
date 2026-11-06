"""Byte-normalized allocation-size follow-up using active observation code."""
import importlib.util
import json
import math
import os
import pathlib
import random
import subprocess
import sys

ROOT=pathlib.Path('/work')
EXP=ROOT/'experiments/allocation-size-v361-v1'
BUILD=ROOT/'build/allocation-size-v361-v1'
OUT=ROOT/'results/allocation-size-v361-v1'
VERSIONS=['v2.1.2','v3.5.0','v3.5.3','v3.6.0','v3.6.1']
SIZES=[4096,16384,65536,262144]
MIB=2**20
def load(p):return json.loads(p.read_text())
def controller():
    spec=importlib.util.spec_from_file_location('size_controller',BUILD/'controller.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.EXP=EXP;m.BUILD=BUILD
    return m
def config(v,s,total,rep=0):
    return dict(version=v,size=s,cap=128*MIB,pairs=2,objects=total//s,retained=False,rep=rep,delay=1000)
def prepare():
    assert not (EXP/'plan.json').exists() and not (EXP/'artifacts.json').exists()
    EXP.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    # Keep the verified delay getter and controller; freeze their provenance.
    parent=ROOT/'build/purge-delay-v361-v1'
    prior=load(ROOT/'experiments/purge-delay-v361-v1/plan.json')
    import hashlib
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(parent/'controller.py')==prior['generated_controller_sha256']
    assert sha(parent/'concurrent.cpp')==prior['generated_source_sha256']
    (BUILD/'controller.py').write_text((parent/'controller.py').read_text())
    source=(parent/'concurrent.cpp').read_text()
    assert source.count('constexpr size_t batch=256;')==1
    source=source.replace('constexpr size_t batch=256;','static size_t batch=0;')
    source=source.replace('object_bytes<64||object_bytes>4096',
        '(object_bytes!=4096&&object_bytes!=16384&&object_bytes!=65536&&object_bytes!=262144)')
    needle='  if((pair_count!=1&&pair_count!=2)'
    assert source.count(needle)==1
    source=source.replace(needle,'  batch=(object_bytes==0 ? 0 : 262144/object_bytes);\n'+needle)
    cpp=BUILD/'concurrent.cpp';cpp.write_text(source)
    con=controller();a=load(ROOT/'experiments/purge-delay-v361-v1/artifacts.json')
    for v in VERSIONS:
        lib=a['libraries'][v];assert con.sha(lib['path'])==lib['sha256']
        src=ROOT/('extern/mimalloc-'+v)
        git=['git','-c','safe.directory='+str(src),'-C',str(src)]
        assert con.cmd(git+['rev-parse','HEAD'])==lib['commit']
        assert not con.cmd(git+['status','--porcelain','--untracked-files=no'])
    cmd=['g++','-std=c++17','-O3','-DNDEBUG','-Wall','-Wextra','-Werror','-fno-builtin-malloc','-fno-builtin-free',str(cpp),'-pthread','-ldl','-o',str(BUILD/'concurrent')]
    subprocess.run(cmd,check=True)
    asm=con.cmd(['objdump','-d','-C',str(BUILD/'concurrent')])
    assert all(x in asm for x in ['<malloc@plt>','<free@plt>','<memset@plt>'])
    (BUILD/'assembly.txt').write_text(asm)
    a['binary']=dict(path=str(BUILD/'concurrent'),sha256=con.sha(BUILD/'concurrent'),command=cmd)
    a['source_sha256']=con.sha(cpp)
    a['parent_artifacts_sha256']=con.sha(ROOT/'experiments/purge-delay-v361-v1/artifacts.json')
    a['environment_current']=dict(kernel=con.cmd(['uname','-a']),cpu=con.cmd(['lscpu']),
        thp=con.read('/sys/kernel/mm/transparent_hugepage/enabled'),cgroup=con.cg(),allowed_cpus=sorted(os.sched_getaffinity(0)))
    con.save(EXP/'artifacts.json',a)
    files=['docs/v361-plan.md','observation/allocation_size_v361.py']
    con.save(EXP/'preparation.json',dict(hashes={p:con.sha(ROOT/p) for p in files},
        controller_sha256=con.sha(BUILD/'controller.py'),source_sha256=con.sha(cpp),artifacts_sha256=con.sha(EXP/'artifacts.json')))
    print('Prepared: common binary, fixed 256 KiB handoff batch',flush=True)
def verify():
    con=controller();p=load(EXP/'preparation.json')
    for f,h in p['hashes'].items():assert con.sha(ROOT/f)==h
    assert con.sha(BUILD/'controller.py')==p['controller_sha256']
    assert con.sha(BUILD/'concurrent.cpp')==p['source_sha256']
    assert con.sha(EXP/'artifacts.json')==p['artifacts_sha256']
    return con
def execute(stage,configs,idle,full=False):
    con=verify();os.sched_setaffinity(0,{10})
    for i,c in enumerate(configs):
        path=OUT/stage/('{:03d}.json'.format(i))
        if path.exists():
            r=load(path);assert r['valid'] and r['config']==c;continue
        r=con.run(c,idle,full)
        r['runtime_policy']='delay1000-arena-mult1-other-defaults'
        r['mimalloc_environment']={'MIMALLOC_PURGE_DELAY':'1000','MIMALLOC_ARENA_PURGE_MULT':'1'}
        r['preparation_sha256']=con.sha(EXP/'preparation.json')
        if stage=='measured':r['plan_sha256']=con.sha(EXP/'plan.json')
        con.save(path,r);assert r['valid'],(str(path),r.get('error'),r.get('stderr'))
        t=r['final']['elapsed_ns']/1e9
        print(stage,i+1,len(configs),c['version'],c['size']//1024,'KiB',round(t,3),'s',round(c['objects']*c['size']/2**30/t,2),'GiB/s',flush=True)
def freeze():
    con=verify();assert not (EXP/'plan.json').exists()
    rows=[load(p) for p in sorted((OUT/'pilot').glob('*.json'))]
    smoke=[load(p) for p in sorted((OUT/'smoke').glob('*.json'))]
    assert len(rows)==len(smoke)==20 and all(r['valid'] for r in rows+smoke)
    rate=max(r['config']['objects']*r['config']['size']/(r['final']['elapsed_ns']/1e9) for r in rows)
    total=max(8*2**30,int(math.ceil(rate*3.5/(128*MIB)))*128*MIB)
    rng=random.Random(2026103103);order=[]
    for rep in range(3):
        block=[config(v,s,total,rep) for v in VERSIONS for s in SIZES];rng.shuffle(block);order.extend(block)
    con.save(EXP/'plan.json',dict(status='Frozen',frozen_at=con.stamp(),preparation_sha256=con.sha(EXP/'preparation.json'),
        seed=2026103103,total_bytes=total,order=order,pilot_hashes={str(p.relative_to(ROOT)):con.sha(p) for p in sorted((OUT/'pilot').glob('*.json'))}))
    print('Frozen total GiB per run:',total/2**30,flush=True)
def main():
    assert sorted(os.sched_getaffinity(0))==[0,2,4,6,8,10]
    action=sys.argv[1]
    if action=='prepare':prepare()
    elif action in ('smoke','pilot'):
        total=256*MIB if action=='smoke' else 8*2**30
        execute(action,[config(v,s,total) for v in VERSIONS for s in SIZES],.01,action=='smoke')
    elif action=='freeze':freeze()
    elif action=='measured':
        con=verify();p=load(EXP/'plan.json');assert con.sha(EXP/'preparation.json')==p['preparation_sha256']
        execute(action,p['order'],1)
    else:raise ValueError(action)
if __name__=='__main__':main()
