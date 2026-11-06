"""Security profile experiment on one pinned dev3 commit (Python 3.6)."""
import copy,json,math,os,pathlib,random,re,subprocess,sys
import dev3_20261106 as prior
ROOT=prior.ROOT; EXP=ROOT/'experiments/security-20261106-v1';OUT=ROOT/'results/security-20261106-v1';BUILD=ROOT/'build/security-20261106-v1'
con,life=prior.con,prior.life
prior.EXP=EXP;prior.OUT=OUT;prior.BUILD=BUILD
con.EXP=EXP/'concurrent';con.OUT=OUT/'concurrent';con.BUILD=BUILD/'concurrent'
life.EXP=EXP/'lifecycle';life.RESULTS=OUT/'lifecycle';life.BUILD=BUILD/'lifecycle'
prior.base.EXP=EXP;prior.base.OUT=OUT;prior.base.BUILD=BUILD
PROFILES=['OFF','MINIMAL','CHECKED','ON','FULL','CHECKED_PAC_WEAK']
LEVEL=dict(OFF=0,MINIMAL=1,CHECKED=2,ON=4,FULL=5,CHECKED_PAC_WEAK=2)
SHA='d6716d33671c2f621b87be3c7ac016c6ba6b3c94';MIB=2**20
def load(p):return json.loads(p.read_text())
def build():
    assert not (EXP/'plan.json').exists()
    BUILD.mkdir(parents=True,exist_ok=True)
    src=ROOT/'extern/mimalloc-dev3-d6716d33';git=['git','-c','safe.directory='+str(src),'-C',str(src)]
    assert con.cmd(git+['rev-parse','HEAD'])==SHA and not con.cmd(git+['status','--porcelain','--untracked-files=no'])
    a=dict(image_id=life.IMAGE,libraries={},environment=dict(kernel=con.cmd(['uname','-a']),cpu=con.cmd(['lscpu']),
      topology=con.cmd(['lscpu','-e']),rocky=con.read('/etc/rocky-release'),compiler=con.cmd(['g++','--version']),
      glibc=con.cmd(['ldd','--version']),thp=con.read('/sys/kernel/mm/transparent_hugepage/enabled'),cgroup=con.cg()))
    for profile in PROFILES:
        secure='CHECKED' if profile=='CHECKED_PAC_WEAK' else profile;pac='WEAK' if profile=='CHECKED_PAC_WEAK' else 'OFF'
        d=BUILD/profile
        cmd=['cmake','-S',str(src),'-B',str(d),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG',
          '-DMI_OVERRIDE=ON','-DMI_BUILD_SHARED=ON','-DMI_BUILD_STATIC=OFF','-DMI_BUILD_OBJECT=OFF','-DMI_BUILD_TESTS=OFF',
          '-DMI_SECURE='+secure,'-DMI_MTE=OFF','-DMI_PAC='+pac]
        with (BUILD/(profile+'-build.log')).open('w') as f:
            subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
            subprocess.run(['cmake','--build',str(d),'--parallel','4'],stdout=f,stderr=subprocess.STDOUT,check=True)
        libs=list(d.glob('libmimalloc*.so'));assert len(libs)==1,libs
        lib=libs[0].resolve();flags=(d/'CMakeFiles/mimalloc.dir/flags.make').read_text()
        assert '-DMI_SECURE='+str(LEVEL[profile]) in flags
        assert ('-DMI_PAC=1' in flags)==(pac=='WEAK')
        a['libraries'][profile]=dict(path=str(lib),sha256=con.sha(lib),commit=SHA,mi_version=30602,
            profile=profile,secure_level=LEVEL[profile],pac=pac,cmake_command=cmd,cmake_cache=(d/'CMakeCache.txt').read_text(),flags=flags)
        print('built',profile,flush=True)
    for name,source,dest in [('lifecycle','lifecycle.cpp',life.BUILD),('concurrent','concurrent.cpp',con.BUILD),('local_batch','local_batch.cpp',BUILD/'local')]:
        dest.mkdir(parents=True,exist_ok=True);binary=dest/name
        cmd=['g++','-std=c++17','-O3','-DNDEBUG','-Wall','-Wextra','-Werror','-fno-builtin-malloc','-fno-builtin-free',str(ROOT/'observation'/source),'-pthread','-ldl','-o',str(binary)]
        subprocess.run(cmd,check=True);assembly=con.cmd(['objdump','-d',str(binary)])
        assert '<malloc@plt>' in assembly and '<free@plt>' in assembly
        b=copy.deepcopy(a);b['binary']=dict(path=str(binary),sha256=con.sha(binary),command=cmd);b['source_sha256']=con.sha(ROOT/'observation'/source)
        # The existing protocol controller reads threads/artifacts; this binary creates no threads.
        con.save(EXP/('threads' if name=='local_batch' else name)/'artifacts.json',b)
    logs={}
    binary=BUILD/'local/local_batch'
    for profile in PROFILES:
        env={k:v for k,v in os.environ.items() if not k.startswith('MIMALLOC_') and k!='LD_PRELOAD'}
        env.update(LD_PRELOAD=a['libraries'][profile]['path'],MIMALLOC_VERBOSE='1')
        r=subprocess.run([str(binary),'1','64','2'],input='gq',stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,universal_newlines=True,timeout=20)
        con.save(EXP/'mode-validation'/(profile+'.json'),dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
        assert r.returncode==0,(profile,r.stderr)
        assert re.search(r'secure level:\s*'+str(LEVEL[profile])+r'\b',r.stderr),(profile,r.stderr)
        if profile=='CHECKED_PAC_WEAK':assert 'weak (process key)' in r.stderr
        logs[profile]=dict(valid=True,secure_level=LEVEL[profile],pac=a['libraries'][profile]['pac'])
    con.save(EXP/'mode-validation.json',logs)

def config(v,size,n,rep=0):return dict(version=v,size=size,cap=128*MIB,pairs=2,objects=n,retained=False,rep=rep)
def localconfig(v,size,n,rep=0):return dict(version=v,size=size,mode=1,cycles=n,rep=rep)
def local(stage,entries):
    for i,c in enumerate(entries):
        p=OUT/'local'/stage/('{:03d}.json'.format(i))
        if p.exists():
            r=load(p);assert r['valid'] and r['config']==c;continue
        r=prior.thread_run(c);con.save(p,r);assert r['valid'],(str(p),r.get('error'),r['stderr'])
        print('local',stage,i+1,len(entries),c['version'],c['size'],round(r['final']['elapsed_ns']/1e9,3),flush=True)
def freeze():
    assert not (EXP/'plan.json').exists()
    pilots={k:[load(p) for p in sorted((OUT/k/'pilot').glob('*.json'))] for k in ('local','concurrent')}
    assert all(len(rs)==12 and all(r['valid'] for r in rs) for rs in pilots.values())
    smoke=list(OUT.glob('*/smoke/*.json'));assert len(smoke)==30 and all(load(p)['valid'] for p in smoke)
    rng=random.Random(2026110602);plans={'local':[],'concurrent':[],'lifecycle':[]}
    for family in ('local','concurrent'):
        for size in (64,4096):
            rows=[r for r in pilots[family] if r['config']['size']==size];key='cycles' if family=='local' else 'objects'
            rates=[r['config'][key]/(r['final']['elapsed_ns']/1e9) for r in rows]
            n=math.ceil(min(max(rates)*3,min(rates)*12))
            n=max(1000,n) if family=='local' else max(1024*MIB//size,int(math.ceil(n/512))*512)
            for rep in range(5):
                vs=PROFILES[:];rng.shuffle(vs)
                plans[family].extend((localconfig if family=='local' else config)(v,size,n,rep) for v in vs)
    for rep in range(3):
        vs=PROFILES[:];rng.shuffle(vs);plans['lifecycle'].extend(dict(version=v,mode='same',rep=rep) for v in vs)
    files=[ROOT/p for p in ('docs/security-20261106-plan.md','observation/security_20261106.py','observation/local_batch.cpp',
      'observation/dev3_20261106.py','observation/release_v361.py','observation/run.py','observation/run_concurrent.py',
      'observation/lifecycle.cpp','observation/concurrent.cpp')]
    files+=list(EXP.glob('*/artifacts.json'))+[EXP/'mode-validation.json']+list(OUT.glob('*/pilot/*.json'))+smoke
    con.save(EXP/'plan.json',dict(status='Frozen',frozen_at=con.stamp(),seed=2026110602,
        hashes={str(p.relative_to(ROOT)):con.sha(p) for p in files},**plans))
    print('Frozen: 60 local + 60 remote + 18 lifecycle',flush=True)
def main():
    assert sorted(os.sched_getaffinity(0))==[0,2,4,6,8,10]
    action=sys.argv[1]
    if action=='build':build();return
    if action=='freeze':freeze();return
    os.sched_setaffinity(0,{10})
    if action=='smoke':
        local('smoke',[localconfig(v,s,5) for s in (64,4096) for v in PROFILES])
        entries=[config(v,s,8*MIB//s) for s in (64,4096) for v in PROFILES]
        for c in entries:c['cap']=2*MIB
        con.execute('smoke',entries,.01,True)
        prior.base.lifecycle('smoke',[dict(version=v,mode='same') for v in PROFILES],64,.05)
    elif action=='pilot':
        local('pilot',[localconfig(v,s,10000) for s in (64,4096) for v in PROFILES])
        con.execute('pilot',[config(v,s,1024*MIB//s) for s in (64,4096) for v in PROFILES],.01)
    elif action=='measured':
        plan=load(EXP/'plan.json');assert plan['status']=='Frozen'
        for p,h in plan['hashes'].items():assert con.sha(ROOT/p)==h,p
        local('measured',plan['local']);con.execute('measured',plan['concurrent'],1)
        prior.base.lifecycle('measured',plan['lifecycle'],32768,1)
    else:raise ValueError(action)
if __name__=='__main__':main()
