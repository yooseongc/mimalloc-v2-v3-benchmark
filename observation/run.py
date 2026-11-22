#!/usr/bin/env python3
"""Fresh implementation: sequential lifecycle controller and external observer."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import random
import select
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP = ROOT / 'experiments/memory-behavior-v1'
BUILD = ROOT / 'build/observation-v1'
RESULTS = ROOT / 'results/memory-behavior-v1'
VERSIONS = {'v2.1.2': ('43ce4bd7fd34bcc730c1c7471c99995597415488', 212),
            'v3.5.0': ('18b08671c9302247bfb682286e6bf3cc1773f801', 30500),
            'v3.5.3': ('d4881d338125e1cb7c47ba4cfb398d6f7c0c8d45', 30503)}
IMAGE = 'sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877'

def sha(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)
def command(args): return subprocess.check_output(args, universal_newlines=True).strip()
def read(path):
    try: return pathlib.Path(path).read_text().strip()
    except OSError: return None

def throttled():
    value=read('/sys/fs/cgroup/cpu.stat')
    if value:
        for line in value.splitlines():
            if line.startswith('nr_throttled '): return int(line.split()[1])
    return None

def build():
    BUILD.mkdir(parents=True, exist_ok=True)
    artifacts = {'image_id': IMAGE, 'libraries': {}}
    for version, (commit, number) in VERSIONS.items():
        src = ROOT / ('extern/mimalloc-' + version)
        git = ['git', '-c', 'safe.directory='+str(src), '-C', str(src)]
        assert command(git+['rev-parse', 'HEAD']) == commit
        assert not command(git+['status', '--porcelain', '--untracked-files=no'])
        directory = BUILD/version
        opts = ['MI_OVERRIDE=ON', 'MI_BUILD_SHARED=ON', 'MI_BUILD_STATIC=OFF',
                'MI_BUILD_OBJECT=OFF', 'MI_BUILD_TESTS=OFF', 'MI_SECURE=OFF']
        cmake_source = (src/'CMakeLists.txt').read_text()
        assert all(opt.split('=')[0] in cmake_source for opt in opts)
        args = ['cmake', '-S', str(src), '-B', str(directory),
                '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG']
        args += ['-D'+opt for opt in opts]
        log = BUILD/(version+'-build.log')
        with log.open('w') as f:
            subprocess.run(args, stdout=f, stderr=subprocess.STDOUT, check=True)
            subprocess.run(['cmake', '--build', str(directory), '--parallel', '4'], stdout=f, stderr=subprocess.STDOUT, check=True)
        lib = directory/'libmimalloc.so'
        assert lib.exists()
        artifacts['libraries'][version] = dict(commit=commit, mi_version=number,
            path=str(lib.resolve()), sha256=sha(lib), cmake_command=args,
            cmake_cache=(directory/'CMakeCache.txt').read_text())
    args = ['g++', '-std=c++17', '-O3', '-DNDEBUG', '-Wall', '-Wextra', '-Werror',
            '-fno-builtin-malloc', '-fno-builtin-free', str(ROOT/'observation/lifecycle.cpp'),
            '-pthread', '-ldl', '-o', str(BUILD/'lifecycle')]
    subprocess.run(args, check=True)
    artifacts['binary'] = dict(path=str(BUILD/'lifecycle'), sha256=sha(BUILD/'lifecycle'), command=args)
    artifacts['source_sha256'] = sha(ROOT/'observation/lifecycle.cpp')
    artifacts['environment'] = dict(kernel=command(['uname', '-a']), rocky=read('/etc/rocky-release'),
        compiler=command(['g++', '--version']), glibc=command(['ldd', '--version']),
        cpu=command(['lscpu']), topology=command(['lscpu','-e=CPU,CORE,SOCKET,NODE']),
        meminfo=read('/proc/meminfo'), thp=read('/sys/kernel/mm/transparent_hugepage/enabled'),
        allowed_cpus=sorted(os.sched_getaffinity(0)), cpu_max=read('/sys/fs/cgroup/cpu.max'),
        cpuset_mems=read('/sys/fs/cgroup/cpuset.mems.effective'), memory_max=read('/sys/fs/cgroup/memory.max'))
    save(EXP/'artifacts.json', artifacts)
    print('Built fresh libraries and lifecycle program', flush=True)

def memory(pid, accurate=False):
    started = time.monotonic()
    status = read('/proc/{}/status'.format(pid))
    if status is None: raise RuntimeError('target disappeared')
    fields = {}
    for line in status.splitlines():
        parts = line.split()
        if parts[0] in ('VmRSS:', 'VmHWM:', 'VmSwap:'):
            fields[parts[0][:-1]] = int(parts[1])*1024
    if accurate:
        smaps = read('/proc/{}/smaps_rollup'.format(pid))
        if smaps:
            for line in smaps.splitlines():
                if line.split()[0] in ('Rss:', 'Pss:', 'AnonHugePages:'):
                    fields[line.split()[0][:-1]] = int(line.split()[1])*1024
    fields.update(t=time.monotonic(), observation_started=started)
    return fields

def run_one(version, mode, n, idle, sampling=True, intervention='none'):
    artifacts = json.loads((EXP/'artifacts.json').read_text())
    lib = artifacts['libraries'][version]
    assert sha(lib['path']) == lib['sha256'] and sha(BUILD/'lifecycle') == artifacts['binary']['sha256']
    env = {k:v for k,v in os.environ.items() if not k.startswith('MIMALLOC_') and k != 'LD_PRELOAD'}
    env['LD_PRELOAD'] = lib['path']
    p = subprocess.Popen([str(BUILD/'lifecycle'), str(n), '4096'], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, universal_newlines=True, bufsize=1)
    record = dict(version=version, mode=mode, object_count=n, object_bytes=4096,
        idle_seconds=idle, sampling=sampling, intervention=intervention,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(), phases=[], checkpoints=[], samples=[], valid=False)
    record['throttled_before']=throttled()
    deadline = time.monotonic()+120
    def response():
        while time.monotonic()<deadline:
            if select.select([p.stdout], [], [], .02)[0]:
                line = p.stdout.readline()
                if not line: raise RuntimeError('target exited unexpectedly')
                return json.loads(line)
            if sampling: record['samples'].append(memory(p.pid))
        raise RuntimeError('target timeout')
    def checkpoint(name, live):
        value = memory(p.pid, True); value.update(name=name, live_bytes=live*4096)
        record['checkpoints'].append(value)
    def phase(name, action, worker, live, affected=None):
        p.stdin.write('{} {}\n'.format(action,worker)); p.stdin.flush()
        value = response()
        assert value['action']==action and value['worker']==worker
        assert value['cpu_start']==value['cpu_end']==(0 if worker==0 else 2)
        assert value['live_objects']==live and value['live_bytes']==live*4096
        if affected is not None: assert value['affected']==affected
        value['name']=name; record['phases'].append(value)
        checkpoint(name, live)
        return value
    try:
        initial=response(); assert initial['version']==lib['mi_version']
        assert pathlib.Path(initial['library']).resolve()==pathlib.Path(lib['path']).resolve()
        maps=read('/proc/{}/maps'.format(p.pid))
        loaded={line.split()[-1] for line in maps.splitlines() if 'libmimalloc' in line}
        assert loaded=={lib['path']}, loaded
        record['ready']=initial; record['library_sha256']=lib['sha256']
        phase('warm_A',7,0,0); phase('warm_B',7,1,0)
        for i in range(6): phase('empty_'+str(i),0,i%2,0,0)
        checkpoint('baseline',0)
        phase('allocate',1,0,n,n); phase('write',2,0,n,n)
        expected=1216+sum((i*37+11)%251 for i in range(n))*4096
        assert phase('verify_all',6,0,n)['checksum']==expected
        freer=0 if mode=='same' else 1
        phase('free_half',3,freer,n//2,n//2)
        expected+=sum((i*37+11)%251 for i in range(1,n,2))*4096
        assert phase('verify_survivors',6,0,n//2)['checksum']==expected
        freed=phase('free_rest',4,freer,0,n//2)
        origin=freed['end_ns']/1e9
        if intervention!='none':
            phase(intervention, 8 if intervention=='collect_normal' else 9, 0,0)
        for offset in [x for x in [.01,.1,1.,5.,30.] if x<idle]+[idle]:
            while time.monotonic()<origin+offset:
                time.sleep(min(.02,max(0,origin+offset-time.monotonic())))
                if sampling: record['samples'].append(memory(p.pid))
            checkpoint('idle_'+str(offset),0)
            record['checkpoints'][-1]['since_free_seconds']=record['checkpoints'][-1]['t']-origin
        phase('reallocate',1,0,n,n); phase('rewrite',2,0,n,n)
        expected+=sum((i*37+11)%251 for i in range(n))*4096
        assert phase('verify_reuse',6,0,n)['checksum']==expected
        phase('final_free',5,freer,0,n)
        p.stdin.write('quit\n'); p.stdin.flush()
        assert p.wait(timeout=5)==0
        record['throttled_after']=throttled()
        assert record['throttled_before']==record['throttled_after']
        assert all(c.get('VmSwap') in (None,0) for c in record['checkpoints'])
        record['valid']=True
    except Exception as e:
        record['error']=repr(e)
        p.kill(); p.wait()
    finally:
        record['stderr']=p.stderr.read()
        record['duration_seconds']=time.monotonic()-(deadline-120)
    return record

def execute(stage):
    os.sched_setaffinity(0,{6})
    plan=json.loads((EXP/'plan.json').read_text())
    if stage=='measured':
        assert plan['design_status']=='Frozen' and plan['execution_enabled']
        assert sha(ROOT/'observation/lifecycle.cpp')==plan['source_sha256']
        assert sha(ROOT/'observation/run.py')==plan['runner_sha256']
        assert sha(EXP/'artifacts.json')==plan['artifacts_sha256']
        order=plan['execution_order']; n=32768; idle=30
    else:
        n=64 if stage=='smoke' else 32768; idle=.05 if stage=='smoke' else 1
        order=[dict(version=v,mode=m,sampling=s) for v in VERSIONS for m in ['same','remote']
               for s in ([True] if stage=='smoke' else [True,False])]
        random.Random(20260922).shuffle(order)
    destination=RESULTS/stage; destination.mkdir(parents=True,exist_ok=True)
    for i,entry in enumerate(order):
        path=destination/('{:02d}.json'.format(i+1))
        if path.exists():
            old=json.loads(path.read_text()); assert old['valid']
            continue
        row=run_one(entry['version'],entry['mode'],n,idle,entry['sampling'])
        row['plan_sha256']=sha(EXP/'plan.json'); row['stage']=stage; row['order']=i+1
        save(path,row)
        print('{} {}/{} {} {} valid={}'.format(stage,i+1,len(order),entry['version'],entry['mode'],row['valid']),flush=True)
        if not row['valid']: raise RuntimeError(row['error'])

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('stage',choices=['build','smoke','pilot','measured'])
    args=parser.parse_args()
    if args.stage=='build': build()
    else: execute(args.stage)
