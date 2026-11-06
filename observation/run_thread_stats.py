"""Build a tiny diagnostic against each version's own headers; no performance runs."""
import hashlib,json,os,pathlib,subprocess
ROOT=pathlib.Path('/work'); OUT=ROOT/'experiments/thread-stats-v1/clean'; BUILD=ROOT/'build/thread-stats-v1'
OUT.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
prior=json.loads((ROOT/'experiments/memory-behavior-v1/artifacts.json').read_text())
results=[]
for v in ['v2.1.2','v3.5.0','v3.5.3']:
    src=ROOT/('extern/mimalloc-'+v); b=BUILD/v
    # Older defaults do not count malloc statistics; enable MI_STAT=1 diagnostically.
    if v!='v3.5.3':
        args=['cmake','-S',str(src),'-B',str(b),'-DCMAKE_BUILD_TYPE=Release',
              '-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG -DMI_STAT=1','-DMI_BUILD_SHARED=ON',
              '-DMI_BUILD_STATIC=OFF','-DMI_BUILD_OBJECT=OFF','-DMI_BUILD_TESTS=OFF','-DMI_SECURE=OFF']
        with (BUILD/(v+'-build.log')).open('w') as f:
            subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,check=True)
            subprocess.run(['cmake','--build',str(b),'--parallel','4'],stdout=f,stderr=subprocess.STDOUT,check=True)
        library=str((b/'libmimalloc.so').resolve())
    else:
        library=prior['libraries'][v]['path'];assert sha(library)==prior['libraries'][v]['sha256']
    binary=BUILD/('probe-'+v)
    subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I'+str(src/'include'),
                    str(ROOT/'observation/thread_stats.cpp'),'-pthread','-ldl','-o',str(binary)],check=True)
    policies=['default','keep-thread'] if v=='v3.5.3' else ['default']
    for policy in policies:
        for remote in (0,1):
            for size in (64,4096):
                env={k:x for k,x in os.environ.items() if not k.startswith('MIMALLOC_') and k!='LD_PRELOAD'}
                if policy=='keep-thread':env['MIMALLOC_COLLECT_MERGES_STATS']='0'
                args=[str(binary),library,'1000',str(size),str(remote),'1' if v=='v2.1.2' else '0']
                r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,universal_newlines=True,timeout=30)
                name='{}-{}-{}-{}'.format(v,policy,size,remote)
                (OUT/(name+'.txt')).write_text(r.stdout+r.stderr)
                parsed=[json.loads(line[5:]) for line in r.stdout.splitlines() if line.startswith('JSON ')]
                results.append(dict(name=name,version=v,policy=policy,size=size,remote=bool(remote),
                    library=library,library_sha256=sha(library),binary_sha256=sha(binary),exit_code=r.returncode,
                    snapshots=parsed,log=name+'.txt',stats_build='default' if v=='v3.5.3' else 'MI_STAT=1'))
                print(name,'exit',r.returncode,parsed,flush=True)
with (OUT/'results.json').open('w') as f:json.dump(dict(source_sha256=sha(ROOT/'observation/thread_stats.cpp'),results=results),f,indent=2)
