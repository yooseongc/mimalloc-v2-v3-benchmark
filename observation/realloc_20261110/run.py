import sys, os, pathlib, json, subprocess, select, time, math, random, statistics, hashlib
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'observation'))
import run_concurrent as util
EXP=ROOT/'experiments/realloc-20261110-v1'
OUT=ROOT/'results/realloc-20261110-v1'
BUILD=ROOT/'build/realloc-20261110-v1'
VERSIONS={'before':'90d604b8d53ade9873387db5295304893816144e',
          'strict':'b28854bfea271b531c8d0da52acd72194845117b',
          'tail':'1af6580b14dc9f7604d6a417a058ca0ef803b29c'}
CELLS=[(a,s,f) for a in (0,1) for s in (4096,8*2**20) for f in (15,12,4)]
save,sha,cmd=util.save,util.sha,util.cmd

def build():
    BUILD.mkdir(parents=True,exist_ok=True)
    artifacts={'libraries':{},'image':'sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877'}
    cache=ROOT/'extern/mimalloc-dev3-realloc-20261110-cache'
    for v,commit in VERSIONS.items():
        src=ROOT/('extern/mimalloc-dev3-realloc-20261110-'+v)
        if not src.exists():
            subprocess.run(['git','-c','safe.directory='+str(cache),'clone','--no-hardlinks','--no-checkout',str(cache),str(src)],check=True)
            subprocess.run(['git','-c','safe.directory='+str(src),'-C',str(src),'checkout','--detach',commit],check=True)
        git=['git','-c','safe.directory='+str(src),'-C',str(src)]
        assert cmd(git+['rev-parse','HEAD'])==commit
        assert not cmd(git+['status','--porcelain','--untracked-files=no'])
        b=BUILD/v
        opts=['MI_OVERRIDE=ON','MI_BUILD_SHARED=ON','MI_BUILD_STATIC=OFF','MI_BUILD_OBJECT=OFF','MI_BUILD_TESTS=OFF','MI_SECURE=OFF','MI_MTE=OFF','MI_PAC=OFF']
        source=(src/'CMakeLists.txt').read_text()
        assert all(x.split('=')[0] in source for x in opts)
        args=['cmake','-S',str(src),'-B',str(b),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']+['-D'+x for x in opts]
        with (BUILD/(v+'-build.log')).open('w') as log:
            subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True)
            subprocess.run(['cmake','--build',str(b),'--parallel','2'],stdout=log,stderr=subprocess.STDOUT,check=True)
        lib=(b/'libmimalloc.so').resolve()
        artifacts['libraries'][v]=dict(commit=commit,path=str(lib),sha256=sha(lib),command=args,cache=(b/'CMakeCache.txt').read_text(),describe=cmd(git+['describe','--always','--tags']),source_status=cmd(git+['status','--porcelain','--untracked-files=no']),header_sha256=sha(src/'include/mimalloc.h'))
        print('built',v,flush=True)
    args=['g++','-std=c++17','-O3','-DNDEBUG','-Wall','-Wextra','-Werror','-fno-builtin-malloc','-fno-builtin-free','-fno-builtin-realloc',str(ROOT/'observation/realloc_20261110/probe.cpp'),'-ldl','-o',str(BUILD/'probe')]
    subprocess.run(args,check=True)
    asm=cmd(['objdump','-d','-C',str(BUILD/'probe')]); assert all(x in asm for x in ('<realloc@plt>','<malloc@plt>','<free@plt>'))
    artifacts['binary']=dict(path=str(BUILD/'probe'),sha256=sha(BUILD/'probe'),command=args)
    artifacts['environment']={k:cmd(v) for k,v in {'kernel':['uname','-a'],'compiler':['g++','--version'],'glibc':['ldd','--version'],'cpu':['lscpu'],'topology':['lscpu','-e'],'rpm':['rpm','-qa'],'numa':['numactl','--hardware']}.items()}
    artifacts['environment'].update(cgroup=util.cg(),thp=util.read('/sys/kernel/mm/transparent_hugepage/enabled'),thp_defrag=util.read('/sys/kernel/mm/transparent_hugepage/defrag'),meminfo=util.read('/proc/meminfo'),time=util.stamp())
    save(EXP/'artifacts.json',artifacts)

def run(cfg):
    art=json.loads((EXP/'artifacts.json').read_text()); lib=art['libraries'][cfg['version']]
    assert sha(lib['path'])==lib['sha256'] and sha(art['binary']['path'])==art['binary']['sha256']
    env={k:v for k,v in os.environ.items() if not k.startswith('MIMALLOC_') and k!='LD_PRELOAD'};env['LD_PRELOAD']=lib['path']
    args=[art['binary']['path']]+[str(cfg[k]) for k in ('api','size','count','fraction','cycles','life','full')]
    rec=dict(config=cfg,valid=False,timestamp=util.stamp(),command=args,cgroup_before=util.cg(),library_sha256=lib['sha256'],binary_sha256=art['binary']['sha256'],mimalloc_environment={},checkpoints={})
    p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,universal_newlines=True)
    def response():
        assert select.select([p.stdout],[],[],120)[0], 'timeout'
        return json.loads(p.stdout.readline())
    def go(): p.stdin.write('g');p.stdin.flush()
    def point(name):
        rec['checkpoints'][name]=util.memory(p.pid,True)
        for line in util.read('/proc/{}/smaps_rollup'.format(p.pid)).splitlines():
            if line.startswith('LazyFree:'):rec['checkpoints'][name]['LazyFree']=int(line.split()[1])*1024
        assert 'LazyFree' in rec['checkpoints'][name]
    try:
        ready=response();rec['ready']=ready
        assert ready['version']==30602 and pathlib.Path(ready['library']).resolve()==pathlib.Path(lib['path']).resolve()
        assert sorted(os.sched_getaffinity(p.pid))==[0]
        maps=util.read('/proc/{}/maps'.format(p.pid));rec['loaded_libraries']=sorted({x.split()[-1] for x in maps.splitlines() if 'libmimalloc' in x})
        assert rec['loaded_libraries']==[lib['path']]
        point('baseline');go()
        if cfg['life']:
            rec['allocated']=response();assert rec['allocated']['phase']=='allocated';point('allocated');go()
            rec['shrunk']=response();assert rec['shrunk']['phase']=='shrunk';point('shrunk')
            time.sleep(1 if not cfg['full'] else .01);point('idle');go()
            assert response()['phase']=='collected';point('collected');go()
        rec['done']=response();assert rec['done']['phase']=='done';point('freed')
        assert sorted(os.sched_getaffinity(p.pid))==[0]
        go();assert p.wait(timeout=10)==0
        n=cfg['count'];f=rec['done'];expected=cfg['cycles']*sum(2*(i%251+1) for i in range(n))
        assert f['checksum']==expected and f['calls']==cfg['cycles']*n and f['live']==0
        rec['cgroup_after']=util.cg();assert util.throttle(rec['cgroup_before'])==util.throttle(rec['cgroup_after'])
        assert all(x['Swap']==x['VmSwap']==0 for x in rec['checkpoints'].values())
        assert int(rec['cgroup_after'].get('memory.swap.current') or 0)==0
        for key in ('oom','oom_kill'):
            before=dict(line.split() for line in rec['cgroup_before']['memory.events'].splitlines())
            after=dict(line.split() for line in rec['cgroup_after']['memory.events'].splitlines())
            assert before[key]==after[key]
        rec['valid']=True
    except Exception as e:
        rec['error']=repr(e);p.kill();p.wait()
    finally:
        rec['stderr']=p.stderr.read();rec['exit_code']=p.returncode
        for stream in (p.stdin,p.stdout,p.stderr):stream.close()
    return rec

def config(v,cell,cycles=1,life=1,full=0,rep=0):
    a,s,f=cell
    return dict(version=v,api=a,size=s,fraction=f,count=128*2**20//s,cycles=cycles,life=life,full=full,rep=rep)

def execute(stage,configs):
    os.sched_setaffinity(0,{2})
    for i,c in enumerate(configs):
        path=OUT/stage/('{:04d}.json'.format(i))
        if path.exists():
            r=json.loads(path.read_text());assert r['valid'] and r['config']==c
        else:
            r=run(c);save(path,r);assert r['valid'],(str(path),r.get('error'),r['stderr'])
        print(stage,i+1,len(configs),c['version'],c['api'],c['size'],c['fraction'],'life',c['life'],round(r['done']['wall_ns']/1e6,3),'ms',flush=True)

def freeze():
    assert not (EXP/'plan.json').exists()
    pilots=[json.loads(p.read_text()) for p in sorted((OUT/'pilot').glob('*.json'))]
    smokes=[json.loads(p.read_text()) for p in sorted((OUT/'smoke').glob('*.json'))]
    assert len(pilots)==len(smokes)==36 and all(r['valid'] for r in pilots+smokes)
    rng=random.Random(20261110);entries=[]
    for cell in CELLS:
        rows=[r for r in pilots if tuple(r['config'][k] for k in ('api','size','fraction'))==cell]
        cycles=min(64,max(4,int(math.ceil(max(5e9/r['done']['loop_ns'] for r in rows)))))
        for rep in range(5):
            vs=list(VERSIONS);rng.shuffle(vs)
            for v in vs:
                entries.append(config(v,cell,rep=rep));entries.append(config(v,cell,cycles=cycles,life=0,rep=rep))
    files=[ROOT/'docs/realloc-20261110-plan.md',EXP/'artifacts.json']+list((ROOT/'observation/realloc_20261110').glob('*.*'))+list(OUT.glob('smoke/*.json'))+list(OUT.glob('preflight/*.json'))+list(OUT.glob('pilot/*.json'))+[ROOT/'observation/run_concurrent.py']
    plan=dict(status='Frozen',frozen_at=util.stamp(),seed=20261110,entries=entries,hashes={str(p.relative_to(ROOT)):sha(p) for p in files})
    save(EXP/'plan.json',plan); print('Frozen',len(entries),flush=True)

def analyze():
    rows=[json.loads(p.read_text()) for p in sorted((OUT/'measured').glob('*.json'))]
    plan=json.loads((EXP/'plan.json').read_text());assert len(rows)==len(plan['entries']) and all(r['valid'] for r in rows)
    summary=[]
    def stats(xs):return dict(median=statistics.median(xs),min=min(xs),max=max(xs))
    for cell in CELLS:
        for v in VERSIONS:
            rs=[r for r in rows if r['config']['version']==v and tuple(r['config'][k] for k in ('api','size','fraction'))==cell]
            life=[r for r in rs if r['config']['life']];cost=[r for r in rs if not r['config']['life']]
            x=dict(api=cell[0],size=cell[1],fraction=cell[2],version=v,repeats=len(life),cycles=cost[0]['config']['cycles'])
            x['ns_per_call']=stats([r['done']['wall_ns']/r['done']['calls'] for r in cost]);x['cpu_ns_per_call']=stats([r['done']['cpu_ns']/r['done']['calls'] for r in cost])
            x['cost_timed_ms']=stats([r['done']['wall_ns']/1e6 for r in cost]);x['moved_fraction']=stats([r['done']['moved']/r['done']['calls'] for r in cost])
            x['usable_mib']=stats([r['shrunk']['usable']/2**20 for r in life]);x['requested_mib']=stats([r['allocated']['requested_after']/2**20 for r in life])
            x['rss_mib']={k:stats([r['checkpoints'][k]['Rss']/2**20 for r in life]) for k in life[0]['checkpoints']}
            x['anon_huge_mib']={k:stats([r['checkpoints'][k]['AnonHugePages']/2**20 for r in life]) for k in life[0]['checkpoints']}
            x['lazy_free_mib']={k:stats([r['checkpoints'][k].get('LazyFree',0)/2**20 for r in life]) for k in life[0]['checkpoints']}
            x['peak_mib']=stats([r['checkpoints']['freed']['VmHWM']/2**20 for r in life])
            x['minor_faults_per_call']=stats([r['done']['minor_faults']/r['done']['calls'] for r in cost])
            summary.append(x)
    ratios=[]
    for cell in CELLS:
        for numerator,denominator in [('strict','before'),('tail','before'),('tail','strict')]:
            vals=[]
            for rep in range(5):
                pair={r['config']['version']:r for r in rows if not r['config']['life'] and r['config']['rep']==rep and tuple(r['config'][k] for k in ('api','size','fraction'))==cell}
                vals.append(pair[numerator]['done']['wall_ns']/pair[denominator]['done']['wall_ns'])
            ratios.append(dict(cell=cell,numerator=numerator,denominator=denominator,ratio=stats(vals)))
    save(EXP/'summary.json',dict(cells=summary,paired_ratios=ratios,valid_runs=len(rows),raw_hashes={str(p.relative_to(ROOT)):sha(p) for p in OUT.glob('measured/*.json')}))
    lines=['# realloc 측정 집계','','총 {} valid runs. 시간은 비용 반복의 batch aggregate / calls 중앙값. RSS는 별도 lifecycle 프로세스 중앙값.'.format(len(rows)),'','|API|크기|남긴 비율|버전|ns/call|이동 %|usable MiB|할당 RSS|축소 RSS|1초 RSS|collect RSS|','|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|']
    for x in summary:
        lines.append('|{}|{}|{}/16|{}|{:.1f}|{:.0f}|{:.2f}|{:.2f}|{:.2f}|{:.2f}|{:.2f}|'.format('aligned' if x['api'] else 'realloc',x['size'],x['fraction'],x['version'],x['ns_per_call']['median'],100*x['moved_fraction']['median'],x['usable_mib']['median'],*[x['rss_mib'][k]['median'] for k in ('allocated','shrunk','idle','collected')]))
    (EXP/'summary.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True)

if __name__=='__main__':
    action=sys.argv[1]
    if action=='build':build()
    elif action=='smoke':execute(action,[config(v,c,full=1) for c in CELLS for v in VERSIONS])
    elif action=='pilot':execute(action,[config(v,c,cycles=4,life=0) for c in CELLS for v in VERSIONS])
    elif action=='preflight':execute(action,[config(v,(0,8*2**20,12),full=1) for v in VERSIONS])
    elif action=='freeze':freeze()
    elif action=='measured':
        plan=json.loads((EXP/'plan.json').read_text());assert plan['status']=='Frozen'
        for p,h in plan['hashes'].items():assert sha(ROOT/p)==h,p
        execute(action,plan['entries'])
    elif action=='analyze':analyze()
    else:raise ValueError(action)
