"""Describe frozen concurrent observations without subtracting control costs."""
import collections
import hashlib
import json
import pathlib
import statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/concurrency-v1'
OUT=ROOT/'docs/concurrency'
VERSIONS=['v2.1.2','v3.5.0','v3.5.3']
COLORS=['#667085','#087f8c','#cc5b20']
CELLS=[(4096,128),(64,128),(256,128),(1024,128),(4096,512)]
MIB=2**20

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    with p.open('w',encoding='utf-8',newline='\n') as f: f.write(json.dumps(x,indent=2)+'\n')
def desc(xs): return dict(median=statistics.median(xs),minimum=min(xs),maximum=max(xs),values=xs)
def label(s,c): return '{} / {} MiB'.format(str(s)+' B' if s<1024 else str(s//1024)+' KiB',c)
def key(r):
    c=r['config'];return c['size'],c['cap']//MIB,c['pairs'],c['version']

def metrics(r):
    cfg=r['config']; n=cfg['objects']; f=r['final']; points=r['checkpoints']; t=f['elapsed_ns']/1e9
    live=[s['progress']['live_estimate_bytes']/MIB for s in r['samples']
          if .1*t < s['progress']['elapsed_ns']/1e9 < .9*t]
    a,b=points[0],points[1]
    return dict(seconds=t,mobjects_sec=n/t/1e6,gib_sec=n*cfg['size']/t/2**30,
        worker_cpu_ns_object=f['cpu_ns']/n,
        producer_cpu_ns_object=sum(w['cpu_ns'] for w in f['workers'] if w['role']=='producer')/n,
        consumer_cpu_ns_object=sum(w['cpu_ns'] for w in f['workers'] if w['role']=='consumer')/n,
        producer_waits_object=sum(w['wait_polls'] for w in f['workers'] if w['role']=='producer')/n,
        consumer_waits_object=sum(w['wait_polls'] for w in f['workers'] if w['role']=='consumer')/n,
        ready_rss_mib=a['Rss']/MIB,done_rss_mib=b['Rss']/MIB,idle_rss_mib=points[-1]['Rss']/MIB,
        sampled_peak_rss_mib=max([s['memory']['VmRSS'] for s in r['samples']]+[a['Rss'],b['Rss']])/MIB,
        process_hwm_mib=max(p['VmHWM'] for p in points)/MIB,
        ready_thp_mib=a['AnonHugePages']/MIB,done_thp_mib=b['AnonHugePages']/MIB,
        minor_faults=b['minor_faults']-a['minor_faults'],major_faults=b['major_faults']-a['major_faults'],
        middle_live_median_mib=statistics.median(live) if live else None)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    plan=json.loads((EXP/'plan.json').read_text()); artifacts=json.loads((EXP/'artifacts.json').read_text())
    assert sha(ROOT/'docs/concurrency-plan.md')==plan['design_revision']
    assert sha(ROOT/'observation/concurrent.cpp')==plan['source_sha256']
    assert sha(ROOT/'observation/run_concurrent.py')==plan['runner_sha256']
    assert sha(EXP/'artifacts.json')==plan['artifacts_sha256']
    by_stage={}; manifest=[]
    for stage in ('measured','controls'):
        paths=sorted((ROOT/'results/concurrency-v1'/stage).glob('*.json'))
        assert len(paths)==len(plan[stage])
        rows=[]
        for p,cfg in zip(paths,plan[stage]):
            r=json.loads(p.read_text()); assert r['valid'] and r['exit_code']==0 and r['config']==cfg
            assert r['binary_sha256']==artifacts['binary']['sha256']
            assert r['library_sha256']==artifacts['libraries'][cfg['version']]['sha256']
            rows.append(r);manifest.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
        by_stage[stage]=rows
    groups=collections.defaultdict(list)
    for r in by_stage['measured']:groups[key(r)].append(r)
    controls={key(r):r for r in by_stage['controls']}
    summary=[]
    for (size,cap,pairs,version),rows in sorted(groups.items()):
        assert len(rows)==3
        values=[metrics(r) for r in rows]; ctr=metrics(controls[(size,cap,pairs,version)])
        stat={k:desc([r[k] for r in values]) for k in values[0]}
        summary.append(dict(size=size,cap_mib=cap,pairs=pairs,version=version,metrics=stat,
            retained_control=ctr,control_speed_ratio=ctr['mobjects_sec']/stat['mobjects_sec']['median']))
    save(EXP/'summary.json',summary);save(EXP/'raw-manifest.json',manifest)
    lookup={(r['size'],r['cap_mib'],r['pairs'],r['version']):r for r in summary}
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':130})
    fig,axes=plt.subplots(2,5,figsize=(16,7))
    for col,(size,cap) in enumerate(CELLS):
        for row,pairs in enumerate((1,2)):
            ax=axes[row,col]
            for i,v in enumerate(VERSIONS):
                r=lookup[(size,cap,pairs,v)];d=r['metrics']['mobjects_sec']
                ax.bar(i,d['median'],color=COLORS[i],width=.65)
                ax.errorbar(i,d['median'],yerr=[[d['median']-d['minimum']],[d['maximum']-d['median']]],fmt='none',color='#202020',capsize=4)
                ax.scatter(i,r['retained_control']['mobjects_sec'],facecolors='white',edgecolors='#202020',marker='D',s=60,zorder=4)
            ax.set_xticks(range(3),['2.1.2','3.5.0','3.5.3']);ax.set_ylim(bottom=0)
            ax.set_title(label(size,cap)+'\n{} pair{}'.format(pairs,'s' if pairs==2 else ''))
            if col==0:ax.set_ylabel('Million completed objects / s')
            ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    fig.suptitle('Concurrent allocation, full write, cross-thread validation and free\nBars: median of 3 runs; whiskers: range. Open diamonds: retained-buffer control, n=1.',y=1.02)
    fig.tight_layout();fig.savefig(OUT/'throughput.png',bbox_inches='tight');fig.savefig(OUT/'throughput.svg',bbox_inches='tight');plt.close(fig)
    fig,axes=plt.subplots(2,5,figsize=(16,7))
    for col,(size,cap) in enumerate(CELLS):
        for row,pairs in enumerate((1,2)):
            ax=axes[row,col]
            for i,v in enumerate(VERSIONS):
                rs=groups[(size,cap,pairs,v)]
                for j,r in enumerate(rs):
                    a=r['checkpoints'][0];t=r['final']['elapsed_ns']/1e9
                    xs=[0]+[s['progress']['elapsed_ns']/1e9/t for s in r['samples']]+[1]
                    ys=[a['Rss']/MIB]+[s['memory']['VmRSS']/MIB for s in r['samples']]+[r['checkpoints'][1]['Rss']/MIB]
                    ax.plot(xs,ys,color=COLORS[i],alpha=.65,lw=.8,label=v if j==0 else None)
            ax.axhline(cap,color='#222',ls=':',lw=.7,label='Requested cap')
            ax.set_xlim(0,1.02);ax.set_ylim(bottom=0);ax.set_title(label(size,cap)+' / {} pair{}'.format(pairs,'s' if pairs==2 else ''))
            if col==0:ax.set_ylabel('Process RSS (MiB)')
            if row==1:ax.set_xlabel('Fraction of each run duration')
    axes[0,0].legend(fontsize=8);fig.suptitle('Memory during continued work; each line is one run (3 per version)\nTime is normalized; durations differ. Dotted line is the payload cap, not actual live bytes.',y=1.02)
    fig.tight_layout();fig.savefig(OUT/'rss.png',bbox_inches='tight');fig.savefig(OUT/'rss.svg',bbox_inches='tight');plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(13,7))
    for col,(size,cap) in enumerate([(64,128),(4096,128),(4096,512)]):
        for row,pairs in enumerate((1,2)):
            ax=axes[row,col]
            for i,v in enumerate(VERSIONS):
                r=sorted(groups[(size,cap,pairs,v)],key=lambda x:x['final']['elapsed_ns'])[1]
                t=r['final']['elapsed_ns']/1e9
                xs=[0]+[s['progress']['elapsed_ns']/1e9/t for s in r['samples']]
                ax.plot(xs,[r['checkpoints'][0]['Rss']/MIB]+[s['memory']['VmRSS']/MIB for s in r['samples']],color=COLORS[i],lw=1.4,label=v)
                ax.plot(xs,[cap]+[s['progress']['live_estimate_bytes']/MIB for s in r['samples']],color=COLORS[i],lw=1,ls='--',alpha=.8)
            ax.set_title(label(size,cap)+' / {} pair{}'.format(pairs,'s' if pairs==2 else ''))
            ax.set_ylim(bottom=0);ax.set_xlim(0,1.02)
            if col==0:ax.set_ylabel('MiB')
            if row==1:ax.set_xlabel('Fraction of each run duration')
    axes[0,0].legend(fontsize=8)
    fig.suptitle('The cap is not the sustained live set\nSolid: process RSS. Dashed: estimated live payload. Each version uses its median-duration run.',y=1.02)
    fig.tight_layout();fig.savefig(OUT/'live-vs-rss.png',bbox_inches='tight');fig.savefig(OUT/'live-vs-rss.svg',bbox_inches='tight');plt.close(fig)
    lines=['# 동시 처리 관찰 수치','', '각 값은 3회 중앙값 [최소–최대]. retained는 별도 1회다.','',
           '| 객체 / 상한 | 쌍 | 버전 | 처리량 (M객체/s) | CPU ns/객체 | 준비 RSS | 작업 후 RSS | idle 5s RSS | 작업 중 생존량 중앙값 |',
           '|---|---:|---|---:|---:|---:|---:|---:|---:|']
    for size,cap in CELLS:
        for pairs in (1,2):
            for v in VERSIONS:
                r=lookup[(size,cap,pairs,v)]; m=r['metrics']; t=m['mobjects_sec']
                vals=[m[k]['median'] for k in ['worker_cpu_ns_object','ready_rss_mib','done_rss_mib','idle_rss_mib','middle_live_median_mib']]
                lines.append('| {} | {} | {} | {:.2f} [{:.2f}–{:.2f}] | {} |'.format(label(size,cap),pairs,v,t['median'],t['minimum'],t['maximum'],' | '.join('{:.2f}'.format(x) for x in vals)))
    lines+=['','RSS·생존량 단위는 MiB. 작업 중 생존량은 각 실행의 10–90% 시간대 샘플 중앙값을 구한 뒤 3회 중앙값을 낸 값이다.',
            'CPU에는 malloc/free·쓰기·검증·인계·busy wait가 포함된다. 개별 allocator 호출 시간이 아니다.','',
            '| 객체 / 상한 | 쌍 | v3.5.3 / v3.5.0 처리량 | v3.5.0 / v2.1.2 처리량 | v3.5.3 / v2.1.2 처리량 |',
            '|---|---:|---:|---:|---:|']
    for s,c in CELLS:
        for p in (1,2):
            vs=[lookup[(s,c,p,v)]['metrics']['mobjects_sec']['median'] for v in VERSIONS]
            lines.append('| {} | {} | {:.3f} | {:.3f} | {:.3f} |'.format(label(s,c),p,vs[2]/vs[1],vs[1]/vs[0],vs[2]/vs[0]))
    lines+=['','| 객체 / 상한 | 버전 | 2쌍 / 1쌍 처리량 |','|---|---|---:|']
    for s,c in CELLS:
        for v in VERSIONS:
            lines.append('| {} | {} | {:.3f} |'.format(label(s,c),v,lookup[(s,c,2,v)]['metrics']['mobjects_sec']['median']/lookup[(s,c,1,v)]['metrics']['mobjects_sec']['median']))
    lines+=['','| 객체 / 상한 | 쌍 | 버전 | retained M객체/s | retained / 기본 처리량 |','|---|---:|---|---:|---:|']
    for s,c in CELLS:
        for p in (1,2):
            for v in VERSIONS:
                r=lookup[(s,c,p,v)];lines.append('| {} | {} | {} | {:.2f} | {:.3f} |'.format(label(s,c),p,v,r['retained_control']['mobjects_sec'],r['control_speed_ratio']))
    with (OUT/'tables.md').open('w',encoding='utf-8',newline='\n') as f:f.write('\n'.join(lines)+'\n')
    prep={}
    for stage in ('smoke-v2','pilot'):
        rows=[json.loads(p.read_text()) for p in (ROOT/'results/concurrency-v1'/stage).glob('*.json')]
        assert len(rows)==24 and all(r['valid'] for r in rows)
        if stage=='smoke-v2': assert all(r['command'][-1]=='1' for r in rows)
        prep[stage]=len(rows)
    validation=dict(measured_valid=len(by_stage['measured']),control_valid=len(by_stage['controls']),
        full_payload_smoke_valid=prep['smoke-v2'],pilot_valid=prep['pilot'],
        frozen_hashes_verified=True,raw_sha256_manifest='raw-manifest.json',
        major_faults_total=sum(metrics(r)['major_faults'] for r in by_stage['measured']),
        shortest_seconds=min(metrics(r)['seconds'] for r in by_stage['measured']),
        longest_seconds=max(metrics(r)['seconds'] for r in by_stage['measured']),
        all_three_versions=VERSIONS,
        preflight_failure='smoke/009.json: 1 MiB cap cannot fit two 1 MiB batches for 4 KiB/2 pairs; input rejected. Replaced by complete smoke-v2 at 2 MiB.')
    save(EXP/'validation.json',validation)
    print(json.dumps(validation,indent=2))

if __name__=='__main__':main()
