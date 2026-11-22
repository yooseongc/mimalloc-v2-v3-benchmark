"""Keep the statistics probe fixed and change only the purge delay."""
import hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/work')
previous=json.loads((root/'experiments/thread-stats-v1/clean/results.json').read_text())
reference=next(r for r in previous['results'] if r['version']=='v3.5.3')
binary=root/'build/thread-stats-v1/probe-v3.5.3'
assert hashlib.sha256(binary.read_bytes()).hexdigest()==reference['binary_sha256']
assert hashlib.sha256(pathlib.Path(reference['library']).read_bytes()).hexdigest()==reference['library_sha256']
rows=[]
for delay in ('0','-1'):
    for size,remote,keep in [(64,0,False),(4096,1,False),(4096,1,True)]:
        env={k:v for k,v in os.environ.items() if not k.startswith('MIMALLOC_') and k!='LD_PRELOAD'}
        env['MIMALLOC_PURGE_DELAY']=delay
        if keep:env['MIMALLOC_COLLECT_MERGES_STATS']='0'
        args=[str(binary),reference['library'],'1000',str(size),str(remote),'0']
        text=subprocess.check_output(args,env=env,universal_newlines=True,timeout=30)
        snapshots=[json.loads(s[5:]) for s in text.splitlines() if s.startswith('JSON ')]
        rows.append(dict(purge_delay=delay,size=size,remote=remote,keep_thread=keep,snapshots=snapshots))
        selected=[s for s in snapshots if s['stage'] in ['A_allocated_raw','A_freed_collected','heap_final']]
        print(delay,size,remote,keep,selected)
out=root/'experiments/thread-stats-v1/purge-control.json'
out.write_text(json.dumps(dict(binary_sha256=reference['binary_sha256'],library_sha256=reference['library_sha256'],results=rows),indent=2)+'\n')
