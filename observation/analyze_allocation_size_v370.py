"""Summarize the frozen equal-byte allocation-size experiment."""
import collections
import importlib.util
import json
import pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=pathlib.Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/allocation-size-v370-v1'
OUT=ROOT/'docs/allocation-size-v370'
VERSIONS=['v2.1.2','v3.5.0','v3.5.3','v3.6.0','v3.6.1','v3.7.0']
SIZES=[4096,16384,65536,262144]
COLORS=['#667085','#087f8c','#cc5b20','#7754b5','#d52c59','#0072b2']
spec=importlib.util.spec_from_file_location('base_analysis',ROOT/'observation/analyze_concurrent.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
sha=base.sha
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def fmt(d):return '{:.2f} [{:.2f}–{:.2f}]'.format(d['median'],d['minimum'],d['maximum'])
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    p=load(EXP/'plan.json');prep=load(EXP/'preparation.json');a=load(EXP/'artifacts.json')
    assert sha(EXP/'preparation.json')==p['preparation_sha256']
    for f,h in prep['hashes'].items():assert sha(ROOT/f)==h
    assert sha(EXP/'artifacts.json')==prep['artifacts_sha256']
    for f,key in [('controller.py','controller_sha256'),('concurrent.cpp','source_sha256')]:
        assert sha(ROOT/'build/allocation-size-v370-v1'/f)==prep[key]
    for f,h in p['pilot_hashes'].items():assert sha(ROOT/f)==h
    assert sha(ROOT/a['binary']['path'].removeprefix('/work/'))==a['binary']['sha256']
    for lib in a['libraries'].values():assert sha(ROOT/lib['path'].removeprefix('/work/'))==lib['sha256']
    groups=collections.defaultdict(list);index=[];counts={}
    for stage,n in [('smoke',24),('pilot',24),('measured',72)]:
        paths=sorted((ROOT/'results/allocation-size-v370-v1'/stage).glob('*.json'));assert len(paths)==n;counts[stage]=n
        for i,path in enumerate(paths):
            r=load(path);c=r['config'];v=c['version']
            assert r['valid'] and r['exit_code']==0
            assert r['preparation_sha256']==sha(EXP/'preparation.json')
            assert r['binary_sha256']==a['binary']['sha256']
            assert r['library_sha256']==a['libraries'][v]['sha256']
            assert r['ready']['purge_delay']==1000 and r['ready']['arena_purge_mult']==1 and r['ready']['purge_decommits']==1
            assert r['final']['live_estimate_bytes']==0
            if stage=='measured':
                assert c==p['order'][i] and r['plan_sha256']==sha(EXP/'plan.json')
                assert c['objects']*c['size']==p['total_bytes']
                groups[(c['size'],v)].append(r)
            elif stage=='smoke':assert r['command'][-1]=='1'
            index.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path)))
    summary=[]
    for (size,v),rs in sorted(groups.items()):
        assert len(rs)==3;values=[]
        for r in rs:
            m=base.metrics(r);t=m['seconds'];cfg=r['config']
            m['middle_rss_mib']=base.statistics.median(s['memory']['VmRSS']/2**20 for s in r['samples'] if .1*t<s['progress']['elapsed_ns']/1e9<.9*t)
            m['worker_cpu_ns_kib']=m['worker_cpu_ns_object']/(size/1024)
            m['timed_new_write_gib_sec']=(cfg['objects']*size-cfg['cap'])/2**30/t
            values.append(m)
        summary.append(dict(size=size,version=v,metrics={k:base.desc([m[k] for m in values]) for k in values[0]}))
    lookup={(s['size'],s['version']):s['metrics'] for s in summary}
    base.save(EXP/'summary.json',summary);base.save(EXP/'raw-index.json',index)
    base.save(EXP/'status.json',dict(status='Complete',counts=counts,invalid=0,excluded=0,
        frozen_hashes_verified=True,total_payload_gib=p['total_bytes']/2**30,
        measured_seconds_range=[min(r['final']['elapsed_ns']/1e9 for rs in groups.values() for r in rs),max(r['final']['elapsed_ns']/1e9 for rs in groups.values() for r in rs)],
        major_faults_total=sum(base.metrics(r)['major_faults'] for rs in groups.values() for r in rs)))
    lines=['# 할당 크기별 관찰 수치','',
        '3회 중앙값 [최소–최대]. 모든 조건의 완료 payload는 {:.3f} GiB, 요청 생존량 상한 128 MiB, 인계 배치 256 KiB다.'.format(p['total_bytes']/2**30),
        'GiB/s는 완료 객체의 요청 크기 합계 기준이며 DRAM 대역폭 계측값이 아니다. 처음 적재한 0.125 GiB는 timed 쓰기 밖이다.','',
        '| 객체 KiB | 버전 | 완료 payload GiB/s | M객체/s | CPU ns/KiB | 작업 중 RSS MiB | 작업 중 생존량 MiB |',
        '|---:|---|---:|---:|---:|---:|---:|']
    for s in summary:lines.append('| {} | {} | {} |'.format(s['size']//1024,s['version'],' | '.join(fmt(s['metrics'][k]) for k in ['gib_sec','mobjects_sec','worker_cpu_ns_kib','middle_rss_mib','middle_live_median_mib'])))
    lines+=['','작업 중 RSS·생존량은 각 실행의 10–90% 시간대 샘플 중앙값을 3회 요약한 값이다. 생존량은 근사치다.','',
        '| 객체 KiB | 버전 | 작업 초 | 완료 RSS MiB | idle 1초 RSS MiB | 완료 THP MiB | minor faults |',
        '|---:|---|---:|---:|---:|---:|---:|']
    for s in summary:lines.append('| {} | {} | {} |'.format(s['size']//1024,s['version'],' | '.join(fmt(s['metrics'][k]) for k in ['seconds','done_rss_mib','idle_rss_mib','done_thp_mib','minor_faults'])))
    lines+=['','| 버전 | 16/4 KiB 바이트 처리량 배수 | 64/4 KiB | 256/4 KiB |','|---|---:|---:|---:|']
    for v in VERSIONS:lines.append('| {} | {} |'.format(v,' | '.join('{:.3f}'.format(lookup[(s,v)]['gib_sec']['median']/lookup[(4096,v)]['gib_sec']['median']) for s in SIZES[1:])))
    (OUT/'tables.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axs=plt.subplots(2,2,figsize=(12,8))
    panels=[('gib_sec','Completed payload (GiB/s)'),('mobjects_sec','Million completed objects / s'),('worker_cpu_ns_kib','Worker CPU ns / KiB'),('middle_rss_mib','Median working RSS (MiB)')]
    for ax,(key,label) in zip(axs.flat,panels):
        for v,color in zip(VERSIONS,COLORS):
            ds=[lookup[(s,v)][key] for s in SIZES];ys=[d['median'] for d in ds]
            ax.errorbar(range(4),ys,yerr=[[d['median']-d['minimum'] for d in ds],[d['maximum']-d['median'] for d in ds]],label=v,color=color,marker='o',capsize=4,lw=1.5)
        ax.set_xticks(range(4),['4','16','64','256']);ax.set_xlabel('Requested object size (KiB)');ax.set_ylabel(label);ax.set_ylim(bottom=0);ax.grid(alpha=.2)
    axs[0,0].legend(ncol=2)
    fig.suptitle('Larger objects: allocation, full write, handoff, validation and remote free\nEqual total payload; 2 pairs; 128 MiB cap; fixed 256 KiB handoff batches. Median and range, n=3.')
    fig.tight_layout();fig.savefig(OUT/'size-sweep.png',dpi=150);fig.savefig(OUT/'size-sweep.svg');plt.close(fig)
    print('Saved allocation-size tables, plots and verified summaries:', OUT)
if __name__=='__main__':main()
