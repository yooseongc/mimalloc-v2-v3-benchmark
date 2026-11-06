"""Read actual policy values, independently of frozen RSS observations."""
import hashlib
import json
import os
import pathlib
import subprocess

ROOT=pathlib.Path('/work')
OUT=ROOT/'experiments/purge-policy-code-analysis'
BUILD=ROOT/'build/purge-policy-code-analysis'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
    OUT.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    source=ROOT/'observation/purge_policy_probe.c'
    artifacts=json.loads((ROOT/'experiments/purge-delay-v1/artifacts.json').read_text())
    rows=[]
    for v in ['v3.5.0','v3.5.3','v3.6.0']:
        lib=artifacts['libraries'][v];assert sha(lib['path'])==lib['sha256']
        binary=BUILD/v
        cmd=['gcc','-I'+str(ROOT/('extern/mimalloc-'+v)/'include'),str(source),lib['path'],
             '-Wl,-rpath,'+str(pathlib.Path(lib['path']).parent),'-o',str(binary)]
        subprocess.run(cmd,check=True)
        env={k:val for k,val in os.environ.items() if not k.startswith('MIMALLOC_') and k!='LD_PRELOAD'}
        env.update(MIMALLOC_PURGE_DELAY='1000',MIMALLOC_ARENA_PURGE_MULT='1',LD_PRELOAD=lib['path'])
        values=json.loads(subprocess.check_output([str(binary)],env=env,universal_newlines=True))
        assert values['version']==lib['mi_version']
        assert values['allow_thp']==(1 if v=='v3.5.0' else 2)
        assert values['minimal_purge_size_option']==0
        assert values['purge_delay']==1000 and values['arena_purge_mult']==1 and values['purge_decommits']==1
        rows.append(dict(version=v,commit=lib['commit'],library_sha256=lib['sha256'],values=values,
                         command=cmd,binary_sha256=sha(binary)))
    result=dict(kind='read-only option probes; not RSS measurements',source_sha256=sha(source),rows=rows,
                thp=(pathlib.Path('/sys/kernel/mm/transparent_hugepage/enabled').read_text().strip()))
    (OUT/'runtime-options.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
