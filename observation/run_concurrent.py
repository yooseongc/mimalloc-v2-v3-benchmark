#!/usr/bin/env python3
"""Independent controller for concurrent batch handoff; Python 3.6 compatible."""
import datetime
import hashlib
import json
import math
import os
import pathlib
import random
import select
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP = ROOT/'experiments/concurrency-v1'
OUT = ROOT/'results/concurrency-v1'
BUILD = ROOT/'build/concurrency-v1'
VERSIONS = ['v2.1.2', 'v3.5.0', 'v3.5.3']
MIB = 1024**2

def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):
    try: return pathlib.Path(p).read_text().strip()
    except OSError: return None
def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2)+'\n')
    tmp.replace(p)
def stamp(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def cmd(a): return subprocess.check_output(a, universal_newlines=True).strip()
def cg():
    result = {}
    for name in ['cpu.stat', 'cpu.max', 'memory.current', 'memory.max', 'memory.swap.current',
                 'memory.events', 'cpuset.cpus.effective', 'cpuset.mems.effective']:
        result[name] = read('/sys/fs/cgroup/'+name)
    return result
def throttle(c):
    return dict(line.split() for line in (c['cpu.stat'] or '').splitlines()).get('nr_throttled')

def build():
    BUILD.mkdir(parents=True, exist_ok=True)
    previous = json.loads((ROOT/'experiments/memory-behavior-v1/artifacts.json').read_text())
    libs = previous['libraries']
    for v in VERSIONS:
        assert sha(libs[v]['path']) == libs[v]['sha256']
        src = ROOT/('extern/mimalloc-'+v)
        git = ['git', '-c', 'safe.directory='+str(src), '-C', str(src)]
        assert cmd(git+['rev-parse', 'HEAD']) == libs[v]['commit']
        assert not cmd(git+['status', '--porcelain', '--untracked-files=no'])
    args = ['g++', '-std=c++17', '-O3', '-DNDEBUG', '-Wall', '-Wextra', '-Werror',
            '-fno-builtin-malloc', '-fno-builtin-free', str(ROOT/'observation/concurrent.cpp'),
            '-pthread', '-ldl', '-o', str(BUILD/'concurrent')]
    subprocess.run(args, check=True)
    assembly = cmd(['objdump', '-d', '-C', str(BUILD/'concurrent')])
    (BUILD/'assembly.txt').write_text(assembly)
    assert '<memset@plt>' in assembly and '<malloc@plt>' in assembly and '<free@plt>' in assembly
    artifact = dict(image_id=previous['image_id'], libraries=libs,
        library_build_provenance='experiments/memory-behavior-v1/artifacts.json',
        library_build_manifest_sha256=sha(ROOT/'experiments/memory-behavior-v1/artifacts.json'),
        binary=dict(path=str(BUILD/'concurrent'), sha256=sha(BUILD/'concurrent'), command=args),
        source_sha256=sha(ROOT/'observation/concurrent.cpp'),
        environment=dict(kernel=cmd(['uname','-a']), compiler=cmd(['g++','--version']),
            glibc=cmd(['ldd','--version']), cpu=cmd(['lscpu']), topology=cmd(['lscpu','-e']),
            rocky=read('/etc/rocky-release'), meminfo=read('/proc/meminfo'),
            thp=read('/sys/kernel/mm/transparent_hugepage/enabled'),
            allowed_cpus=sorted(os.sched_getaffinity(0)), cgroup=cg()))
    save(EXP/'artifacts.json', artifact)
    print('Build and library/source verification passed', flush=True)

def memory(pid, precise=False):
    value = dict(t=time.monotonic())
    for line in read('/proc/{}/status'.format(pid)).splitlines():
        a = line.split()
        if a[0] in ('VmRSS:', 'VmHWM:', 'VmSwap:'): value[a[0][:-1]] = int(a[1])*1024
    if precise:
        for line in read('/proc/{}/smaps_rollup'.format(pid)).splitlines():
            a = line.split()
            if a[0] in ('Rss:', 'Pss:', 'AnonHugePages:', 'Swap:'): value[a[0][:-1]] = int(a[1])*1024
        stat = read('/proc/{}/stat'.format(pid)).split(') ')[1].split()
        value.update(minor_faults=int(stat[7]), major_faults=int(stat[9]))
    return value

def run(cfg, idle=5, full=False):
    a = json.loads((EXP/'artifacts.json').read_text()); lib = a['libraries'][cfg['version']]
    assert sha(lib['path']) == lib['sha256'] and sha(BUILD/'concurrent') == a['binary']['sha256']
    env = {k:v for k,v in os.environ.items() if not k.startswith('MIMALLOC_') and k != 'LD_PRELOAD'}
    env['LD_PRELOAD'] = lib['path']
    args = [str(BUILD/'concurrent')] + [str(cfg[k]) for k in ('pairs','size','cap','objects')]
    args += [str(int(cfg['retained'])), str(int(full))]
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=env, universal_newlines=True, bufsize=1)
    rec = dict(config=cfg, timestamp=stamp(), valid=False, samples=[], checkpoints=[],
               command=args, library_sha256=lib['sha256'], binary_sha256=a['binary']['sha256'],
               runtime_policy='upstream-default', mimalloc_environment={}, cgroup_before=cg())
    deadline = time.monotonic()+180
    def response():
        remain = deadline-time.monotonic()
        if remain <= 0 or not select.select([p.stdout], [], [], remain)[0]: raise RuntimeError('timeout')
        line = p.stdout.readline()
        if not line: raise RuntimeError('unexpected process exit')
        return json.loads(line)
    def request(s):
        p.stdin.write(s+'\n'); p.stdin.flush()
        return response()
    def checkpoint(name):
        point=memory(p.pid, True); point['name']=name; rec['checkpoints'].append(point)
    try:
        r=response(); rec['ready']=r
        assert r['version']==lib['mi_version'] and r['live_bytes']==cfg['cap']
        assert pathlib.Path(r['library']).resolve()==pathlib.Path(lib['path']).resolve()
        loaded={line.split()[-1] for line in read('/proc/{}/maps'.format(p.pid)).splitlines() if 'libmimalloc' in line}
        assert loaded=={lib['path']}, loaded
        rec['thread_affinity']={}
        for tid in (pathlib.Path('/proc')/str(p.pid)/'task').iterdir():
            cpus=sorted(os.sched_getaffinity(int(tid.name)))
            rec['thread_affinity'][tid.name]=cpus
        expected_cpus=[0,2,8] if cfg['pairs']==1 else [0,2,4,6,8]
        assert sorted(x[0] for x in rec['thread_affinity'].values() if len(x)==1)==expected_cpus
        checkpoint('ready')
        assert request('go')['started']
        while True:
            progress=request('sample'); mem=memory(p.pid)
            rec['samples'].append(dict(progress=progress, memory=mem))
            if progress['done']: break
            time.sleep(.1)
        rec['final']=progress; checkpoint('done')
        n=cfg['objects']; pairs=cfg['pairs']; initial=cfg['cap']//cfg['size']; m=n//pairs
        assert progress['produced']==n-initial and progress['consumed']==n
        assert progress['checksum']==(m*m if pairs==1 else 2*m*m+m)
        assert progress['live_estimate_bytes']==(cfg['cap'] if cfg['retained'] else 0)
        for w in progress['workers']:
            cpu=w['pair']*4+(2 if w['role']=='consumer' else 0)
            assert w['cpu_start']==w['cpu_end']==cpu
            assert w['count']==(m if w['role']=='consumer' else m-initial//pairs)
        finished=time.monotonic()
        for delay in sorted(set([min(.1,idle), min(1,idle), idle])):
            time.sleep(max(0,finished+delay-time.monotonic())); checkpoint('idle_'+str(delay))
        p.stdin.write('quit\n');p.stdin.flush();p.wait(timeout=10)
        rec['stderr']=p.stderr.read(); assert p.returncode==0
        rec['cgroup_after']=cg()
        assert throttle(rec['cgroup_before'])==throttle(rec['cgroup_after'])
        assert all(s['memory']['VmSwap']==0 for s in rec['samples'])
        assert all(c['VmSwap']==0 and c['Swap']==0 for c in rec['checkpoints'])
        rec['valid']=True
    except Exception as e:
        rec['error']=repr(e)
        p.kill();p.wait();rec['stderr']=p.stderr.read()
    finally:
        rec['exit_code']=p.returncode
        for stream in (p.stdin,p.stdout,p.stderr): stream.close()
    return rec

def execute(stage, configs, idle=5, full=False):
    for i,cfg in enumerate(configs):
        path=OUT/stage/('{:03d}.json'.format(i))
        if path.exists():
            r=json.loads(path.read_text()); assert r['config']==cfg and r['valid'], str(path)
            continue
        r=run(cfg,idle,full); save(path,r)
        assert r['valid'], (str(path),r.get('error'),r.get('stderr'))
        print('{} {}/{} {} {}B {}MiB {}pairs retained={} {:.3f}s'.format(stage,i+1,len(configs),
            cfg['version'],cfg['size'],cfg['cap']//MIB,cfg['pairs'],cfg['retained'],
            r['final']['elapsed_ns']/1e9),flush=True)

def configs(sizes, cap, total_bytes, retained=False):
    return [dict(version=v,pairs=p,size=s,cap=cap,objects=total_bytes//s,retained=retained)
            for s in sizes for p in (1,2) for v in VERSIONS]

def freeze():
    assert not (EXP/'plan.json').exists(), 'already frozen'
    runs=[json.loads(p.read_text()) for p in sorted((OUT/'pilot').glob('*.json'))]
    assert len(runs)==24 and all(r['valid'] for r in runs)
    counts={}
    for s in (64,256,1024,4096):
        rate=max(r['config']['objects']/(r['final']['elapsed_ns']/1e9) for r in runs if r['config']['size']==s)
        counts[s]=int(math.ceil(rate*3.5/512))*512
        counts[s]=max(counts[s],1024*MIB//s)
    rng=random.Random(20260922); measured=[]; controls=[]
    for size,cap in [(4096,128*MIB),(64,128*MIB),(256,128*MIB),(1024,128*MIB),(4096,512*MIB)]:
        for rep in range(3):
            pairs=[1,2];rng.shuffle(pairs)
            for pair in pairs:
                versions=VERSIONS[:];rng.shuffle(versions)
                for v in versions:
                    measured.append(dict(version=v,pairs=pair,size=size,cap=cap,objects=counts[size],retained=False,rep=rep))
        for pair in (1,2):
            versions=VERSIONS[:];rng.shuffle(versions)
            for v in versions:
                controls.append(dict(version=v,pairs=pair,size=size,cap=cap,objects=counts[size],retained=True,rep=0))
    doc=ROOT/'docs/concurrency-plan.md'
    text=doc.read_text().replace('Design status: Draft','Design status: Frozen')
    text+='\n## Frozen execution details\n\nFrozen at: '+stamp()+'\n\n'
    text+='Object counts: '+json.dumps(counts)+'; random seed: 20260922.\n'
    text+='90 primary runs and 30 retained controls (one control per cell). 3.5 s target based on fastest pilot; controls may finish faster.\n'
    text+='Control runs are descriptive only; one repetition cannot estimate their variability.\n'
    text+='Freeze revision is SHA-256 of this document, stored in experiments/concurrency-v1/plan.json.\n'
    doc.write_text(text)
    plan=dict(status='Frozen',frozen_at=stamp(),design_revision=sha(doc),
        artifacts_sha256=sha(EXP/'artifacts.json'),source_sha256=sha(ROOT/'observation/concurrent.cpp'),
        runner_sha256=sha(__file__),seed=20260922,counts=counts,measured=measured,controls=controls)
    save(EXP/'plan.json',plan)
    print(json.dumps(dict(counts=counts,primary=len(measured),controls=len(controls))),flush=True)

def main():
    action=sys.argv[1]
    assert sorted(os.sched_getaffinity(0))==[0,2,4,6,8,10]
    if action=='build': build(); return
    os.sched_setaffinity(0,{10})
    if action=='smoke':
        execute('smoke-v2',configs([64,4096],2*MIB,8*MIB)+configs([64,4096],2*MIB,8*MIB,True),.01,True)
    elif action=='pilot': execute('pilot',configs([64,256,1024,4096],128*MIB,1024*MIB),.01)
    elif action=='freeze': freeze()
    elif action in ('measured','controls'):
        plan=json.loads((EXP/'plan.json').read_text())
        assert sha(ROOT/'docs/concurrency-plan.md')==plan['design_revision']
        assert sha(EXP/'artifacts.json')==plan['artifacts_sha256']
        assert sha(ROOT/'observation/concurrent.cpp')==plan['source_sha256']
        assert sha(__file__)==plan['runner_sha256']
        execute(action,plan[action])
    else: raise ValueError(action)

if __name__=='__main__': main()
