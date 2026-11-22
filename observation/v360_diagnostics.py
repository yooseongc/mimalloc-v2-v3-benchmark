"""v3.6.0 native stats fields and page layout, separate from timed runs."""
import hashlib
import json
import os
import pathlib
import subprocess

root=pathlib.Path('/work')
out=root/'experiments/release-v360-v1/diagnostics'
build=root/'build/release-v360-v1/diagnostics'
out.mkdir(parents=True,exist_ok=True);build.mkdir(parents=True,exist_ok=True)
art=json.loads((root/'experiments/release-v360-v1/lifecycle/artifacts.json').read_text())
lib=art['libraries']['v3.6.0']
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
assert sha(lib['path'])==lib['sha256']
base=root/'observation/thread_stats_ab.cpp'
text=base.read_text().replace('30503','30600').replace('mi_option_collect_merges_stats','mi_option_stats_merge_on_collect')
text=text.replace('auto n=s.malloc_normal;','auto n=s.allocated;')
text=text.replace(r'\"allocated_count\":%lld}',r'\"allocated_count\":%lld,\"native_free_count\":%lld,\"native_freed_bytes\":%lld}',1)
text=text.replace('(long long)s.malloc_normal_count.total);','(long long)s.malloc_count.total,(long long)s.free_count.total,(long long)s.freed.total);')
text=text.replace(r'\"purge_delay\":%ld',r'\"stats_merge_threshold_bytes\":%zu,\"purge_delay\":%ld')
text=text.replace('API(mi_option_get)(mi_option_purge_delay));','API(mi_option_get_size)(mi_option_stats_merge_threshold),API(mi_option_get)(mi_option_purge_delay));')
source=build/'native-stats.cpp';source.write_text(text)
binary=build/'native-stats'
cmd=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I/work/extern/mimalloc-v3.6.0/include',str(source),'-pthread','-ldl','-o',str(binary)]
subprocess.run(cmd,check=True)
env={k:v for k,v in os.environ.items() if not k.startswith('MIMALLOC_') and k!='LD_PRELOAD'}
env.update(MIMALLOC_STATS_MERGE_ON_COLLECT='0',MIMALLOC_STATS_MERGE_THRESHOLD='0')
records=[]
for size in (64,4096):
    r=subprocess.run([str(binary),lib['path'],str(size)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=20)
    (out/('native-stats-{}.jsonl'.format(size))).write_text(r.stdout)
    (out/('native-stats-{}.stderr'.format(size))).write_text(r.stderr)
    assert r.returncode==0,r.stderr
    rows=[json.loads(s) for s in r.stdout.splitlines()]
    assert rows[0]['collect_merges_stats']==rows[0]['stats_merge_threshold_bytes']==0
    f=next(s for s in rows if s.get('stage')=='both_collected_again')
    assert f['A_free_calls']==f['B_alloc_calls']==0
    assert f['A_alloc_calls']==f['B_free_calls']==1000
    for who in ('A','B','parent'):
        assert f[who]['native_freed_bytes']==f[who]['derived_freed_bytes']
        assert f[who]['native_free_count']*size==f[who]['native_freed_bytes']
    assert sum(f[w]['native_free_count'] for w in ('A','B','parent'))==1000
    records.append(dict(size=size,rows=rows,valid=True))
    print('native counters',size,'A=',f['A']['native_free_count'],'B=',f['B']['native_free_count'],flush=True)
save=dict(library=lib['path'],library_sha256=lib['sha256'],source_sha256=sha(source),base_sha256=sha(base),binary_sha256=sha(binary),command=cmd,records=records)
(out/'native-stats.json').write_text(json.dumps(save,indent=2)+'\n')
# The same official visitor probe as the earlier active layout diagnostic.
source=root/'observation/page_layout.cpp';binary=build/'page-layout'
cmd=['g++','-std=c++17','-O2','-I/work/extern/mimalloc-v3.6.0/include',str(source),'-ldl','-o',str(binary)]
subprocess.run(cmd,check=True)
r=subprocess.run([str(binary),lib['path']],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=20)
(out/'page-layout.json').write_text(r.stdout);(out/'page-layout.stderr').write_text(r.stderr)
assert r.returncode==0,r.stderr
layout=json.loads(r.stdout)
assert layout['version']==30600 and layout['used_total']==256
print('page-layout',len(layout['areas']),'areas',sorted(set(x['reserved']//x['block_size'] for x in layout['areas'])),flush=True)
(out/'page-layout-manifest.json').write_text(json.dumps(dict(command=cmd,source_sha256=sha(source),binary_sha256=sha(binary),library_sha256=lib['sha256']),indent=2)+'\n')
