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

def main():
    exp=ROOT/'experiments/release-v361-v1'
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
        ('release-v361-v1',{'lifecycle/smoke':10,'concurrent/smoke':20,'concurrent/pilot':35,
            'lifecycle/measured':30,'lifecycle/collect':10,'concurrent/measured':105}),
        ('purge-delay-v361-v1',{'defaults':5,'smoke':10,'measured':30}),
        ('allocation-size-v361-v1',{'smoke':20,'pilot':20,'measured':60})]:
        counts[namespace]={}
        for stage,n in stages.items():
            paths=sorted((ROOT/'results'/namespace/stage).glob('*.json'))
            assert len(paths)==n,(namespace,stage,len(paths),n)
            for p in paths:
                r=load(p)
                assert r['valid'],p
                assert r.get('exit_code',0)==0,p
                if stage.endswith('measured') and 'final' in r:
                    durations.append(r['final']['elapsed_ns']/1e9)
                    pts=r['checkpoints']
                    major_faults+=pts[1]['major_faults']-pts[0]['major_faults']
                peak_rss=max(peak_rss,max((c.get('VmHWM',0) for c in r.get('checkpoints',[])),default=0))
            counts[namespace][stage]=n
    stats=load(exp/'stats/results.json')
    assert len(stats)==24 and all(r['valid'] for r in stats)
    summary=load(exp/'summary.json')
    assert len(summary['concurrent'])==35 and len(summary['lifecycle'])==10
    assert len(load(ROOT/'experiments/purge-delay-v361-v1/summary.json'))==10
    assert len(load(ROOT/'experiments/allocation-size-v361-v1/summary.json'))==20
    status=dict(status='Complete',verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        counts=counts,stats=24,invalid=0,excluded=0,plan_sha256=sha(exp/'plan.json'),
        measured_concurrent_seconds_range=[min(durations),max(durations)],
        process_peak_rss_mib=peak_rss/2**20,measured_concurrent_major_faults=major_faults,
        note='Three repetitions per measured cell; descriptive median and range only.')
    save(exp/'status.json',status)
    print(json.dumps(status,indent=2))

if __name__=='__main__':main()
