"""Post-measurement diagnostic; counts only, never used as throughput evidence."""
import json,os,pathlib,subprocess
import security_20261106 as sec
def main():
    a=sec.load(sec.EXP/'threads/artifacts.json');binary=a['binary']
    assert sec.con.sha(binary['path'])==binary['sha256']
    dest=sec.EXP/'syscall-diagnostic';dest.mkdir(parents=True,exist_ok=True)
    assert not (dest/'results.json').exists()
    sec.con.save(dest/'plan.json',dict(created_at=sec.con.stamp(),purpose='Investigate FULL large local cost with syscall counts',
       profiles=['OFF','FULL'],sizes=[64,4096],warmup_batches=100,measured_batches=100,
       repeats=1,scope='whole process including startup and warmup; instrumented times excluded from performance results'))
    # Untimed direct API query in one fresh Python process per library; no results
    # from these processes are used as LD_PRELOAD performance measurements.
    code='import ctypes,json,sys; m=ctypes.CDLL(sys.argv[1]); m.mi_good_size.argtypes=[ctypes.c_size_t]; m.mi_good_size.restype=ctypes.c_size_t; print(json.dumps({"version":m.mi_version(),"64":m.mi_good_size(64),"4096":m.mi_good_size(4096)}))'
    sizes={}
    for v in sec.PROFILES:
        sizes[v]=json.loads(subprocess.check_output(['python3','-c',code,a['libraries'][v]['path']],universal_newlines=True))
        assert sizes[v]['version']==30602
    sec.con.save(dest/'good-sizes.json',sizes)
    results=[]
    for v in ('OFF','FULL'):
        lib=a['libraries'][v];assert sec.con.sha(lib['path'])==lib['sha256']
        for size in (64,4096):
            path=dest/('{}-{}.txt'.format(v,size))
            env={k:x for k,x in os.environ.items() if not k.startswith('MIMALLOC_') and k!='LD_PRELOAD'}
            cmd=['strace','-f','-c','-e','trace=mmap,munmap,mprotect,madvise','-o',str(path),'-E','LD_PRELOAD='+lib['path'],binary['path'],'1',str(size),'100']
            r=subprocess.run(cmd,input='gq',env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=60)
            rec=dict(profile=v,size=size,command=cmd,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr,
                     summary=path.read_text() if path.exists() else None,library_sha256=lib['sha256'],binary_sha256=binary['sha256'])
            if r.returncode==0:
                final=json.loads(r.stdout.splitlines()[-1]);assert final['allocations']==final['frees']==102400
                assert final['checksum']==100*sum(2*(i%251) for i in range(1024)) and final['live_objects']==0
                rec['valid']=True
            else:rec['valid']=False
            results.append(rec);print(v,size,'valid',rec['valid'],flush=True)
    sec.con.save(dest/'results.json',results)
if __name__=='__main__':main()
