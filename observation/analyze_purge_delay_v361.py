"""Validate and describe the frozen purge-delay observation, without pooling old runs."""
import collections
import importlib.util
import json
import pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=pathlib.Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/purge-delay-v361-v1'
OUT=ROOT/'docs/purge-delay-v361'
VERSIONS=['v2.1.2','v3.5.0','v3.5.3','v3.6.0','v3.6.1']
COLORS=['#667085','#087f8c','#cc5b20','#7754b5','#d52c59']
spec=importlib.util.spec_from_file_location('analysis',ROOT/'observation/analyze_concurrent.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
sha=base.sha
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def show(d):return '{:.2f} [{:.2f}–{:.2f}]'.format(d['median'],d['minimum'],d['maximum'])

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    plan=load(EXP/'plan.json');a=load(EXP/'artifacts.json')
    for p,h in plan['hashes'].items():assert sha(ROOT/p)==h,p
    assert sha(EXP/'artifacts.json')==plan['artifacts_sha256']
    for p,key in [('controller.py','generated_controller_sha256'),('concurrent.cpp','generated_source_sha256')]:
        assert sha(ROOT/'build/purge-delay-v361-v1'/p)==plan[key]
    assert sha(ROOT/a['binary']['path'].removeprefix('/work/'))==a['binary']['sha256']
    for lib in a['libraries'].values():assert sha(ROOT/lib['path'].removeprefix('/work/'))==lib['sha256']
    groups=collections.defaultdict(list);manifest=[];counts={}
    for stage,expected in [('defaults',5),('smoke',10),('measured',30)]:
        paths=sorted((ROOT/'results/purge-delay-v361-v1'/stage).glob('*.json'))
        assert len(paths)==expected;counts[stage]=len(paths)
        for i,p in enumerate(paths):
            r=load(p);c=r['config'];v=c['version'];d=c['delay']
            assert r['valid'] and r['exit_code']==0
            assert r['plan_sha256']==sha(EXP/'plan.json')
            assert r['binary_sha256']==a['binary']['sha256']
            assert r['library_sha256']==a['libraries'][v]['sha256']
            assert r['ready']['purge_delay']==(d if d is not None else (10 if v=='v2.1.2' else 1000))
            assert r['ready']['arena_purge_mult']==(1 if d is not None else (10 if v=='v2.1.2' else 4))
            assert r['ready']['purge_decommits']==1
            if stage=='measured':
                assert c==plan['order'][i];groups[(d,v)].append(r)
            else:assert r['command'][-1]=='1'
            manifest.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
    summary=[]
    for (delay,v),rows in sorted(groups.items()):
        assert len(rows)==3
        values=[]
        for r in rows:
            m=base.metrics(r);t=m['seconds']
            m['middle_rss_mib']=base.statistics.median(s['memory']['VmRSS']/2**20 for s in r['samples'] if .1*t<s['progress']['elapsed_ns']/1e9<.9*t)
            for p in r['checkpoints'][2:]:m[p['name']+'_rss_mib']=p['Rss']/2**20
            values.append(m)
        summary.append(dict(delay_ms=delay,arena_purge_mult=1,version=v,metrics={k:base.desc([m[k] for m in values]) for k in values[0]}))
    base.save(EXP/'summary.json',summary);base.save(EXP/'raw-index.json',manifest)
    base.save(EXP/'status.json',dict(status='Complete',counts=counts,invalid=0,excluded=0,frozen_hashes_verified=True,
        premeasurement_failure=None))
    lines=['# 동일 purge 대기시간의 RSS 관찰','', '각 조건 3회 중앙값 [최소–최대]. RSS 단위 MiB. arena_purge_mult=1 공통.','',
           '| delay ms | 버전 | 준비 RSS | 작업 중 RSS | 완료 RSS | idle 5초 RSS | 작업 중 생존량 | 처리량 M객체/s |',
           '|---:|---|---:|---:|---:|---:|---:|---:|']
    keys=['ready_rss_mib','middle_rss_mib','done_rss_mib','idle_rss_mib','middle_live_median_mib','mobjects_sec']
    for s in summary:lines.append('| {} | {} | {} |'.format(s['delay_ms'],s['version'],' | '.join(show(s['metrics'][k]) for k in keys)))
    lines+=['','작업 중 값은 각 실행의 경과시간 10–90% 샘플 중앙값을 구한 뒤 3회 요약한 것이다.',
            '생존량은 비동기 진행 카운터에 따른 근사치다. 처리량에는 할당·전체 쓰기·검증·인계·해제·대기가 모두 포함된다.','',
            '| delay ms | 버전 | idle 0.1초 RSS | idle 1초 RSS | idle 5초 RSS | 작업 중 minor faults |',
            '|---:|---|---:|---:|---:|---:|']
    for s in summary:lines.append('| {} | {} | {} |'.format(s['delay_ms'],s['version'],' | '.join(show(s['metrics'][k]) for k in ['idle_0.1_rss_mib','idle_1_rss_mib','idle_5_rss_mib','minor_faults'])))
    (OUT/'tables.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(12,8),sharey=True)
    for col,d in enumerate((10,1000)):
        for v,color in zip(VERSIONS,COLORS):
            for j,r in enumerate(groups[(d,v)]):
                pts=r['checkpoints'];end=r['final']['elapsed_ns']/1e9
                samples=[s for s in r['samples'] if s['progress']['elapsed_ns']/1e9<end]
                xs=[0]+[s['progress']['elapsed_ns']/1e9 for s in samples]+[end]
                ys=[pts[0]['Rss']/2**20]+[s['memory']['VmRSS']/2**20 for s in samples]+[pts[1]['Rss']/2**20]
                axes[0,col].plot(xs,ys,color=color,lw=1,alpha=.7,label=v if j==0 else None)
                axes[1,col].plot([p['t']-pts[1]['t'] for p in pts[1:]],[p['Rss']/2**20 for p in pts[1:]],color=color,lw=1,alpha=.7,marker='.',label=v if j==0 else None)
        axes[0,col].set_title('purge_delay = {} ms; arena_purge_mult = 1'.format(d))
        axes[0,col].set_xlabel('Seconds since work started')
        axes[1,col].set_xlabel('Seconds since completion was observed')
        for row in (0,1):axes[row,col].set_ylim(bottom=0);axes[row,col].grid(alpha=.2)
    axes[0,0].set_ylabel('Working: process RSS (MiB)');axes[1,0].set_ylabel('Idle: process RSS (MiB)')
    axes[0,0].legend(ncol=2)
    fig.suptitle('1 KiB objects, 2 allocation/free pairs, 128 MiB handoff cap\nEach line: one run; 3 per condition. All objects freed before idle; workers remain alive.')
    fig.tight_layout();fig.savefig(OUT/'rss.png',dpi=150);fig.savefig(OUT/'rss.svg');plt.close(fig)
    print('Saved purge tables, plots and verified summaries:', OUT)

if __name__=='__main__':main()
