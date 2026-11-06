"""Only v3.5.3; strict A-alloc/B-free roles, both alive at every checkpoint."""
import hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/work');out=root/'experiments/thread-stats-ab-v353';out.mkdir(parents=True,exist_ok=True)
build=root/'build/thread-stats-ab-v353';build.mkdir(parents=True,exist_ok=True)
lib=json.loads((root/'experiments/memory-behavior-v1/artifacts.json').read_text())['libraries']['v3.5.3']
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
assert sha(lib['path'])==lib['sha256']
binary=build/'probe';source=root/'observation/thread_stats_ab.cpp'
command=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I/work/extern/mimalloc-v3.5.3/include',str(source),'-pthread','-ldl','-o',str(binary)]
subprocess.run(command,check=True)
results=[]
for policy in ('default','keep-thread'):
    for size in (64,4096):
        for rep in range(2):
            env={k:v for k,v in os.environ.items() if not k.startswith('MIMALLOC_') and k!='LD_PRELOAD'}
            if policy=='keep-thread':env['MIMALLOC_COLLECT_MERGES_STATS']='0'
            run=subprocess.run([str(binary),lib['path'],str(size)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=20)
            name='{}-{}-{}'.format(policy,size,rep)
            (out/(name+'.jsonl')).write_text(run.stdout)
            (out/(name+'.stderr')).write_text(run.stderr)
            assert run.returncode==0,(name,run.returncode,run.stderr)
            lines=[json.loads(s) for s in run.stdout.splitlines()];config=lines.pop(0)
            assert config['collect_merges_stats']==(1 if policy=='default' else 0)
            assert config['purge_delay']==1000
            assert len(lines)==8 and lines[0]['sum']['allocated_bytes']==0
            for s in lines:
                assert s['A_free_calls']==0 and s['B_alloc_calls']==0
                if s['stage'] in ('A_collected_while_live','both_collected_again','both_merged'):
                    assert s['sum']['allocated_bytes']==size*1000 and s['sum']['allocated_count']==1000
                    assert s['sum']['current_bytes']==(size*1000 if s['stage']=='A_collected_while_live' else 0)
            assert lines[-1]['B_free_calls']==1000
            results.append(dict(name=name,config=config,stages=lines,validated=True))
            print(name,'PASS',[(s['stage'],s['A']['derived_freed_bytes'],s['B']['derived_freed_bytes'],s['parent']['derived_freed_bytes'],s['sum']['current_bytes']) for s in lines],flush=True)
(out/'results.json').write_text(json.dumps(dict(library=lib['path'],library_sha256=lib['sha256'],commit=lib['commit'],source_sha256=sha(source),binary_sha256=sha(binary),build_command=command,results=results),indent=2)+'\n')
