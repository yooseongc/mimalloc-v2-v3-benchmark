"""Isolated internal-large-page A/B; uses the frozen active size workload."""
import importlib.util
import json
import math
import os
import pathlib
import random
import shlex
import shutil
import subprocess
import sys

R=pathlib.Path('/work')
NS='v370-large-pages-v1'
E=R/'experiments'/NS
B=R/'build'/NS
O=R/'results'/NS
PROFILES={'v361-default':'v3.6.1','v370-default':'v3.7.0','v370-large':'v3.7.0'}
SIZES=[4096,16384,65536,262144]
MIB=2**20

def load(p): return json.loads(p.read_text())
def module(p):
    spec=importlib.util.spec_from_file_location('controller',p)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.EXP=E;m.BUILD=B
    return m
def cfg(v,s,total,rep=0):
    return dict(version=v,size=s,cap=128*MIB,pairs=2,objects=total//s,retained=False,rep=rep,delay=1000)
def prepare():
    assert not (E/'preparation.json').exists()
    E.mkdir(parents=True,exist_ok=True);B.mkdir(parents=True,exist_ok=True)
    parent=R/'build/allocation-size-v370-v1'
    con=module(parent/'controller.py')
    prep=load(R/'experiments/allocation-size-v370-v1/preparation.json')
    prior=load(R/'experiments/allocation-size-v370-v1/artifacts.json')
    for f,key in [('controller.py','controller_sha256'),('concurrent.cpp','source_sha256')]:
        assert con.sha(parent/f)==prep[key]
        shutil.copyfile(str(parent/f),str(B/f))
    assert con.sha(parent/'concurrent')==prior['binary']['sha256']
    shutil.copy2(str(parent/'concurrent'),str(B/'concurrent'))
    shutil.copyfile(str(R/'experiments/v370-code-analysis-v1/pages.c'),str(B/'pages.c'))
    libs={};pages={}
    for profile,v in PROFILES.items():
        original=prior['libraries'][v];src=R/('extern/mimalloc-'+v)
        git=['git','-c','safe.directory='+str(src),'-C',str(src)]
        assert con.cmd(git+['rev-parse','HEAD'])==original['commit']
        assert not con.cmd(git+['status','--porcelain','--untracked-files=no'])
        dest=B/profile
        command=list(original['cmake_command']);command[command.index('-B')+1]=str(dest)
        command+=['-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']
        if profile=='v370-large':command+=['-DCMAKE_C_FLAGS=-DMI_ENABLE_LARGE_PAGES=1']
        subprocess.run(command,check=True)
        subprocess.run(['cmake','--build',str(dest),'-j','4'],check=True)
        lib=(dest/'libmimalloc.so').resolve()
        flags=dest/'CMakeFiles/mimalloc.dir/flags.make'
        kv=dict(line.split(' = ',1) for line in flags.read_text().splitlines() if ' = ' in line)
        cc=['cc']+sum([shlex.split(kv[k]) for k in ['C_DEFINES','C_INCLUDES','C_FLAGS']],[])
        macros=con.cmd(cc+['-dM','-E',str(B/'pages.c')])
        expected=0 if profile=='v370-default' else 1
        assert '#define MI_ENABLE_LARGE_PAGES '+str(expected) in macros
        (E/(profile+'-macros.txt')).write_text(macros+'\n')
        cmd=cc+[str(B/'pages.c'),'-L'+str(dest),'-Wl,-rpath,'+str(dest),'-lmimalloc','-o',str(B/(profile+'-pages'))]
        subprocess.run(cmd,check=True)
        pages[profile]=dict(command=cmd,observations=[json.loads(x) for x in con.cmd([str(B/(profile+'-pages'))]).splitlines()])
        libs[profile]=dict(commit=original['commit'],upstream_version=v,mi_version=original['mi_version'],path=str(lib),sha256=con.sha(lib),cmake_command=command,cmake_cache=(dest/'CMakeCache.txt').read_text(),flags=flags.read_text(),compile_commands=load(dest/'compile_commands.json'),large_pages=expected)
    con.save(E/'pages.json',pages)
    a=dict(libraries=libs,binary=dict(path=str(B/'concurrent'),sha256=con.sha(B/'concurrent')),image_id=prior['image_id'],environment=dict(kernel=con.cmd(['uname','-a']),cpu=con.cmd(['lscpu']),compiler=con.cmd(['cc','--version']),glibc=con.cmd(['ldd','--version']),thp=con.read('/sys/kernel/mm/transparent_hugepage/enabled'),cgroup=con.cg(),allowed_cpus=sorted(os.sched_getaffinity(0))))
    con.save(E/'artifacts.json',a)
    paths=[R/'docs/v370-large-pages-plan.md',pathlib.Path(__file__).resolve(),B/'controller.py',B/'concurrent.cpp',B/'pages.c',E/'pages.json',E/'artifacts.json']
    con.save(E/'preparation.json',dict(hashes={str(p.relative_to(R)):con.sha(p) for p in paths}))

def verify():
    con=module(B/'controller.py')
    for p,h in load(E/'preparation.json')['hashes'].items():assert con.sha(R/p)==h,p
    return con
def execute(stage,configs):
    con=verify();os.sched_setaffinity(0,{10})
    for i,c in enumerate(configs):
        p=O/stage/('{:03d}.json'.format(i));assert not p.exists()
        r=con.run(c,1 if stage=='measured' else .01,stage=='smoke')
        r['runtime_policy']='delay1000-arena-mult1-other-defaults'
        r['mimalloc_environment']={'MIMALLOC_PURGE_DELAY':'1000','MIMALLOC_ARENA_PURGE_MULT':'1'}
        r['preparation_sha256']=con.sha(E/'preparation.json')
        if stage=='measured':r['plan_sha256']=con.sha(E/'plan.json')
        con.save(p,r);assert r['valid'],(p,r.get('error'),r.get('stderr'))
        t=r['final']['elapsed_ns']/1e9
        print(stage,i+1,len(configs),c['version'],c['size']//1024,round(t,3),round(c['objects']*c['size']/2**30/t,3),flush=True)
def freeze():
    con=verify();assert not (E/'plan.json').exists()
    pilots=[load(p) for p in sorted((O/'pilot').glob('*.json'))]
    smokes=[load(p) for p in sorted((O/'smoke').glob('*.json'))]
    assert len(pilots)==len(smokes)==12 and all(r['valid'] for r in pilots+smokes)
    rate=max(r['config']['objects']*r['config']['size']/(r['final']['elapsed_ns']/1e9) for r in pilots)
    total=max(load(R/'experiments/allocation-size-v370-v1/plan.json')['total_bytes'],int(math.ceil(rate*3.5/(128*MIB)))*128*MIB)
    rng=random.Random(2026111804);order=[]
    for rep in range(3):
        block=[cfg(v,s,total,rep) for v in PROFILES for s in SIZES];rng.shuffle(block);order+=block
    con.save(E/'plan.json',dict(status='Frozen',frozen_at=con.stamp(),preparation_sha256=con.sha(E/'preparation.json'),total_bytes=total,seed=2026111804,order=order,pilot_hashes={str(p.relative_to(R)):con.sha(p) for p in sorted((O/'pilot').glob('*.json'))}))
    print('Frozen GiB',total/2**30,flush=True)
def main():
    assert sorted(os.sched_getaffinity(0))==[0,2,4,6,8,10]
    stage=sys.argv[1]
    if stage=='prepare':prepare()
    elif stage in ('smoke','pilot'):execute(stage,[cfg(v,s,(256*MIB if stage=='smoke' else 8*2**30)) for v in PROFILES for s in SIZES])
    elif stage=='freeze':freeze()
    elif stage=='measured':
        con=verify();p=load(E/'plan.json');assert con.sha(E/'preparation.json')==p['preparation_sha256']
        execute(stage,p['order'])
    else:raise ValueError(stage)
if __name__=='__main__':main()
