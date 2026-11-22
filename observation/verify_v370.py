"""Audit complete new results against frozen plans, and preserve provenance."""
import datetime
import hashlib
import json
import os
import pathlib
import subprocess

ROOT=pathlib.Path(__file__).resolve().parents[1]
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')

def local_path(p):
    return ROOT/p.removeprefix('/work/')

def audit_record(r, artifact):
    """Recheck identity and accounting independently of the valid flag."""
    v=r.get('config',{}).get('version',r.get('version'))
    lib=artifact['libraries'][v]
    assert r['library_sha256']==lib['sha256']
    assert r['ready']['version']==lib['mi_version']
    assert r['ready']['library']==lib['path']
    for c in r['checkpoints']:
        assert c.get('VmSwap',0)==c.get('Swap',0)==0
    if 'config' in r:
        c=r['config']; f=r['final']; n=c['objects']; m=n//c['pairs']
        assert r['binary_sha256']==artifact['binary']['sha256']
        assert f['consumed']==n and f['produced']==n-c['cap']//c['size']
        assert f['checksum']==(m*m if c['pairs']==1 else 2*m*m+m)
        assert f['live_estimate_bytes']==0
        assert len(f['workers'])==2*c['pairs']
        for w in f['workers']:
            cpu=4*w['pair']+(2 if w['role']=='consumer' else 0)
            assert w['cpu_start']==w['cpu_end']==cpu
        for cg in (r['cgroup_before'],r['cgroup_after']):
            assert cg['memory.max']=='6442450944'
            assert cg['cpu.max'].split()[0]=='max'
            assert cg['memory.swap.current']=='0'
        counters=[dict(line.split() for line in r[k]['cpu.stat'].splitlines()) for k in ('cgroup_before','cgroup_after')]
        assert counters[0]['nr_throttled']==counters[1]['nr_throttled']
    else:
        assert r['phases'][-1]['name']=='final_free'
        assert r['phases'][-1]['live_objects']==0
        assert r['throttled_before']==r['throttled_after']
        for p in r['phases']:
            assert p['cpu_start']==p['cpu_end']==2*p['worker']

def main():
    exp=ROOT/'experiments/release-v370-v1'
    plan=load(exp/'plan.json')
    for f,h in dict(plan['hashes'],**plan['pilot_hashes']).items(): assert sha(ROOT/f)==h,f
    libs=load(exp/'lifecycle/artifacts.json')['libraries']
    sources={}
    for v,lib in libs.items():
        src=ROOT/('extern/mimalloc-'+v)
        # Windows cannot faithfully report the Linux checkout executable bits.
        # Build-time Linux checks already verified modes; here verify content.
        git=['git','-c','safe.directory='+str(src)]
        if os.name=='nt':git+=['-c','core.filemode=false']
        git+=['-C',str(src)]
        def cmd(args):return subprocess.check_output(git+args,universal_newlines=True).strip()
        assert cmd(['rev-parse','HEAD'])==lib['commit']
        assert not cmd(['status','--porcelain','--untracked-files=no'])
        sources[v]=dict(commit=lib['commit'],describe=cmd(['describe','--tags','--always']),
            clean_tracked_content=True,windows_filemode_ignored=(os.name=='nt'),header_sha256=sha(src/'include/mimalloc.h'),
            cmake_sha256=sha(src/'CMakeLists.txt'),library_sha256=lib['sha256'])
    save(exp/'sources.json',sources)
    counts={}; durations=[]; peak_rss=0; major_faults=0
    for namespace,stages in [
        ('release-v370-v1',{'lifecycle/smoke':12,'concurrent/smoke':24,'concurrent/pilot':42,
            'lifecycle/measured':36,'lifecycle/collect':12,'concurrent/measured':126}),
        ('purge-delay-v370-v1',{'defaults':6,'smoke':12,'measured':36}),
        ('allocation-size-v370-v1',{'smoke':24,'pilot':24,'measured':72})]:
        counts[namespace]={}
        for stage,n in stages.items():
            artifact_path=ROOT/'experiments'/namespace
            if namespace=='release-v370-v1':artifact_path/=stage.split('/')[0]
            artifact=load(artifact_path/'artifacts.json')
            assert sha(local_path(artifact['binary']['path']))==artifact['binary']['sha256']
            for lib in artifact['libraries'].values():
                assert sha(local_path(lib['path']))==lib['sha256']
            paths=sorted((ROOT/'results'/namespace/stage).glob('*.json'))
            assert len(paths)==n,(namespace,stage,len(paths),n)
            for p in paths:
                r=load(p)
                assert r['valid'],p
                assert r.get('exit_code',0)==0,p
                audit_record(r,artifact)
                if stage.endswith('measured') and 'final' in r:
                    durations.append(r['final']['elapsed_ns']/1e9)
                    pts=r['checkpoints']
                    major_faults+=pts[1]['major_faults']-pts[0]['major_faults']
                peak_rss=max(peak_rss,max((c.get('VmHWM',0) for c in r.get('checkpoints',[])),default=0))
            counts[namespace][stage]=n
    stats=load(exp/'stats/results.json')
    assert len(stats)==32 and all(r['valid'] for r in stats)
    for r in stats:
        assert r['rows'][-1]['sum']['current_bytes']==0
        assert sha(ROOT/'build/release-v370-v1'/('stats-'+r['version']+'.cpp'))==r['source_sha256']
        assert sha(ROOT/'build/release-v370-v1'/('stats-'+r['version']))==r['binary_sha256']
    summary=load(exp/'summary.json')
    assert len(summary['concurrent'])==42 and len(summary['lifecycle'])==12
    assert len(load(ROOT/'experiments/purge-delay-v370-v1/summary.json'))==12
    assert len(load(ROOT/'experiments/allocation-size-v370-v1/summary.json'))==24
    status=dict(status='Complete',verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        counts=counts,stats=32,invalid=0,excluded=0,plan_sha256=sha(exp/'plan.json'),
        measured_concurrent_seconds_range=[min(durations),max(durations)],
        process_peak_rss_mib=peak_rss/2**20,measured_concurrent_major_faults=major_faults,
        note='Three repetitions per measured cell; descriptive median and range only.')
    save(exp/'status.json',status)
    print(json.dumps(status,indent=2))

if __name__=='__main__':main()
