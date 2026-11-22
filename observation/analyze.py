"""Descriptive lifecycle evidence, not a version ranking or significance test."""
import hashlib
import json
import pathlib
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=pathlib.Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/memory-behavior-v1'
OUT=ROOT/'docs/memory-behavior'
VERSIONS=['v2.1.2','v3.5.0','v3.5.3']
COLORS=['#667085','#087f8c','#cc5b20']
STAGES=['baseline','allocate','write','free_half','free_rest','idle_30','reallocate','rewrite']
LABELS=['Start','Allocated','Written','Half freed','All freed','Idle 30s','Allocated\nagain','Written\nagain']

def describe(values):
    return dict(median=statistics.median(values),minimum=min(values),maximum=max(values),values=values)

def main():
    paths=sorted((ROOT/'results/memory-behavior-v1/measured').glob('*.json'))
    rows=[json.loads(p.read_text()) for p in paths]
    plan=json.loads((EXP/'plan.json').read_text())
    digest=hashlib.sha256((EXP/'plan.json').read_bytes()).hexdigest()
    assert len(rows)==18 and all(r['valid'] and r['plan_sha256']==digest for r in rows)
    groups=[]
    for mode in ['same','remote']:
        for version in VERSIONS:
            selected=[r for r in rows if r['version']==version and r['mode']==mode]
            assert len(selected)==3
            runs=[]
            for r in selected:
                p={p['name']:p for p in r['phases']}; c={c['name']:c for c in r['checkpoints']}
                assert c['baseline']['live_bytes']==0 and c['write']['live_bytes']==128*2**20
                assert c['free_half']['live_bytes']==64*2**20 and c['free_rest']['live_bytes']==0
                assert all(x['major_faults']==0 for x in r['phases'])
                run=dict(order=r['order'],rss_mib={s:c[s]['Rss']/2**20 for s in STAGES},
                    anon_huge_mib={s:c[s]['AnonHugePages']/2**20 for s in STAGES},
                    phase_ms={s:p[s]['wall_ns']/1e6 for s in STAGES if s in p},
                    phase_cpu_ms={s:p[s]['cpu_ns']/1e6 for s in STAGES if s in p},
                    phase_minor_faults={s:p[s]['minor_faults'] for s in STAGES if s in p},
                    process_hwm_mib=max(x['VmHWM'] for x in r['checkpoints'])/2**20,
                    idle_actual_seconds=c['idle_30']['since_free_seconds'])
                for metric,stages in [('first_use_ms',['allocate','write']),('free_ms',['free_half','free_rest']),
                                      ('reuse_ms',['reallocate','rewrite'])]:
                    run[metric]=sum(p[s]['wall_ns'] for s in stages)/1e6
                run['idle_retained_above_baseline_mib']=(c['idle_30']['Rss']-c['baseline']['Rss'])/2**20
                run['reuse_rss_growth_mib']=(c['rewrite']['Rss']-c['idle_30']['Rss'])/2**20
                runs.append(run)
            group=dict(version=version,mode=mode,runs=runs)
            for key in ['first_use_ms','free_ms','reuse_ms','idle_retained_above_baseline_mib','reuse_rss_growth_mib']:
                group[key]=describe([r[key] for r in runs])
            group['rss_mib']={s:describe([r['rss_mib'][s] for r in runs]) for s in STAGES}
            group['phase_ms']={s:describe([r['phase_ms'][s] for r in runs]) for s in runs[0]['phase_ms']}
            groups.append(group)
    summary=dict(plan_sha256=digest,valid_flows=len(rows),groups=groups,
                 cpu_time_note='RUSAGE_THREAD returned zero for short free phases; these values are resolution-limited, not zero cost.',
                 interpretation='Three independent runs; descriptive median and full range; no equivalence or superiority test')
    OUT.mkdir(parents=True,exist_ok=True)
    (EXP/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    (EXP/'raw-index.json').write_text(json.dumps([dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths],indent=2)+'\n')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(14,5),sharey=True)
    for ax,mode in zip(axes,['same','remote']):
        for v,color in zip(VERSIONS,COLORS):
            g=next(g for g in groups if g['version']==v and g['mode']==mode)
            for r in g['runs']:
                ax.plot(range(8),[r['rss_mib'][s] for s in STAGES],color=color,alpha=.25,lw=1)
            ax.plot(range(8),[g['rss_mib'][s]['median'] for s in STAGES],'o-',color=color,label=v,lw=2)
        ax.plot(range(8),[0,128,128,64,0,0,128,128],'--',color='#111827',label='Live requested bytes')
        ax.set_xticks(range(8)); ax.set_xticklabels(LABELS,rotation=35,ha='right')
        ax.set_title('A allocates / '+('A frees' if mode=='same' else 'B frees')+' / A allocates again')
        ax.grid(axis='y',alpha=.2); ax.set_ylim(bottom=0); ax.legend(fontsize=9)
    axes[0].set_ylabel('Process RSS / live requested memory (MiB)')
    fig.suptitle('Memory through the lifecycle | 4 KiB objects, 128 MiB requested\nThick: median; thin: all 3 runs. Stage spacing is not elapsed time.',fontsize=12)
    fig.tight_layout()
    for ext in ['svg','png']: fig.savefig(OUT/('memory-phases.'+ext),dpi=160)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(14,4.5),sharey=True)
    for ax,mode in zip(axes,['same','remote']):
        for v,color in zip(VERSIONS,COLORS):
            for i,r in enumerate([r for r in rows if r['version']==v and r['mode']==mode]):
                c=r['checkpoints']; start=next(x['t'] for x in c if x['name']=='baseline')
                c=[x for x in c if x['t']>=start]
                ax.plot([x['t']-start for x in c],[x['Rss']/2**20 for x in c],'.-',alpha=.6,color=color,label=v if i==0 else None)
        ax.set_xscale('symlog',linthresh=.1)
        ax.set_xlabel('Actual seconds since baseline (symlog scale)')
        ax.set_title('Same-thread free' if mode=='same' else 'Cross-thread free')
        ax.grid(alpha=.2);ax.legend()
    axes[0].set_ylabel('Process RSS (MiB)')
    fig.suptitle('Actual checkpoint times | lines connect observations; no unsampled peak is inferred')
    fig.tight_layout()
    for ext in ['svg','png']: fig.savefig(OUT/('timeline.'+ext),dpi=160)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),sharey=True)
    for ax,mode in zip(axes,['same','remote']):
        for j,(v,color) in enumerate(zip(VERSIONS,COLORS)):
            g=next(g for g in groups if g['version']==v and g['mode']==mode)
            xs=[i+(j-1)*.23 for i in range(3)]
            stats=[g[s] for s in ['first_use_ms','free_ms','reuse_ms']]
            ax.bar(xs,[s['median'] for s in stats],width=.21,color=color,label=v)
            for x,s in zip(xs,stats): ax.scatter([x]*3,s['values'],s=18,color='#111827',zorder=4)
        ax.set_xticks(range(3));ax.set_xticklabels(['First alloc + write','Two free phases','Next alloc + write'])
        ax.set_title('Same-thread free' if mode=='same' else 'Cross-thread free');ax.legend();ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Milliseconds for the full object set')
    fig.suptitle('Stage costs | bars: median; dots: individual runs (n=3)')
    fig.tight_layout()
    for ext in ['svg','png']:fig.savefig(OUT/('stage-costs.'+ext),dpi=160)
    plt.close(fig)
    text=['# 새 메모리 흐름 관찰 결과','', 'Execution status: Complete (18/18 valid flows)','',
          '4 KiB 객체 32,768개, 총 요청량 128 MiB를 사용했다. 같은 스레드/다른 스레드 해제 각각에서 세 버전을 새 프로세스로 3회씩 관찰했다. 아래 수치는 중앙값 [최솟값–최댓값]이며, 작은 성능 차이를 확정하는 통계 검정은 하지 않았다.','']
    interpretation=EXP/'interpretation.ko.md'
    if interpretation.exists():text += [interpretation.read_text(encoding='utf-8'),'']
    text += ['## 메모리 흐름','', '프로세스 전체 RSS(MiB) 중앙값이다. 살아 있는 요청량은 시작 0 → 할당/쓰기 128 → 절반 해제 64 → 전체 해제/휴식 0 → 재사용 128 MiB다. RSS는 요청량과 별개이며 남은 양 전체를 누수나 단편화라고 해석하지 않는다.','',
             '| 버전 | 해제 | 시작 | 쓰기 후 | 절반 해제 | 전부 해제 | 30초 휴식 | 재사용 후 |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    for g in groups:
        text.append('| {} | {} | {} |'.format(g['version'],'A' if g['mode']=='same' else 'B', ' | '.join('{:.2f}'.format(g['rss_mib'][s]['median']) for s in ['baseline','write','free_half','free_rest','idle_30','rewrite'])))
    text+=['','![단계별 메모리](memory-behavior/memory-phases.svg)','','![실제 시각별 RSS](memory-behavior/timeline.svg)','','## 단계별 비용','','전체 객체 집합을 처리하는 ms다. 첫 사용과 재사용은 각각 할당+쓰기의 실행별 합을 구한 뒤 중앙값을 냈다. 검증·경계 관찰·인계 대기·30초 휴식은 이 비용에서 제외한다.','',
           '| 버전 | 해제 | 첫 할당+쓰기 | 두 해제 구간 합 | 재할당+쓰기 |','|---|---|---:|---:|---:|']
    fmt=lambda s:'{:.2f} [{:.2f}–{:.2f}]'.format(s['median'],s['minimum'],s['maximum'])
    for g in groups:text.append('| {} | {} | {} |'.format(g['version'],g['mode'],' | '.join(fmt(g[k]) for k in ['first_use_ms','free_ms','reuse_ms'])))
    text+=['','![단계별 비용](memory-behavior/stage-costs.svg)','','할당과 쓰기를 분리한 ms 중앙값:','','| 버전 | 해제 | 첫 할당 | 첫 쓰기 | 재할당 | 재쓰기 |','|---|---|---:|---:|---:|---:|']
    for g in groups:text.append('| {} | {} | {} |'.format(g['version'],g['mode'],' | '.join('{:.2f}'.format(g['phase_ms'][k]['median']) for k in ['allocate','write','reallocate','rewrite'])))
    text+=['','## 실제 페이지 사용과 CPU 비용','','AnonHugePages는 사용된 THP의 관측값이다. 설정 문자열만 보고 사용을 추정하지 않았다. minor fault는 오류가 아니라 페이지 매핑 등을 처리한 횟수다. 아래는 실행별 값의 중앙값이다. 짧은 해제 단계에서 RUSAGE_THREAD CPU 시간이 0으로 보고돼 이 구간의 CPU 비용은 해상도 부족으로 표시했다. CPU 비용이 없다는 뜻이 아니며 해제 시간은 벽시계 측정값으로만 해석한다.','',
           '| 버전 | 해제 | 첫 쓰기 후 THP MiB | 첫 할당 minor faults | 첫 할당+쓰기 CPU ms | 해제 CPU ms | 재할당+쓰기 CPU ms |',
           '|---|---|---:|---:|---:|---:|---:|']
    for g in groups:
        runs=g['runs']; med=statistics.median
        nums=[med(r['anon_huge_mib']['write'] for r in runs),med(r['phase_minor_faults']['allocate'] for r in runs)]
        cells=['{:.2f}'.format(n) for n in nums]
        for phases in [('allocate','write'),('free_half','free_rest'),('reallocate','rewrite')]:
            valid=all(r['phase_cpu_ms'][s]>0 for r in runs for s in phases)
            cells.append('{:.2f}'.format(med(sum(r['phase_cpu_ms'][s] for s in phases) for r in runs)) if valid else '해상도 부족')
        text.append('| {} | {} | {} |'.format(g['version'],g['mode'],' | '.join(cells)))
    collect_paths=sorted((ROOT/'results/memory-behavior-v1/collect-check').glob('*.json'))
    if collect_paths:
        assert len(collect_paths)==6
        probes=[json.loads(p.read_text()) for p in collect_paths]
        assert all(r['valid'] for r in probes)
        text+=['','## 명시적으로 반환시킨 뒤 다시 사용하면','','기본 관찰 이후 선택한 별도 진단이다. 전체 해제 직후 A에서 mi_collect(true)를 한 번 호출했다. 나머지 흐름과 30초 휴식은 같다. 각 조건 한 번이므로 아래 비용은 개별 관측값이며 성능 순위로 사용하지 않는다.','',
               '| 버전 | 해제 | collect 전 RSS MiB | collect 후 RSS MiB | 30초 후 RSS MiB | collect ms | 다음 할당+쓰기 ms |','|---|---|---:|---:|---:|---:|---:|']
        for r in sorted(probes,key=lambda r:(r['mode'],r['version'])):
            c={x['name']:x for x in r['checkpoints']};p={x['name']:x for x in r['phases']}
            values=[c['free_rest']['Rss']/2**20,c['collect_force']['Rss']/2**20,c['idle_30']['Rss']/2**20,
                    p['collect_force']['wall_ns']/1e6,(p['reallocate']['wall_ns']+p['rewrite']['wall_ns'])/1e6]
            text.append('| {} | {} | {} |'.format(r['version'],r['mode'],' | '.join('{:.2f}'.format(n) for n in values)))
        (EXP/'collect-raw-index.json').write_text(json.dumps([dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in collect_paths],indent=2)+'\n')
    text += ['','## 측정 범위와 한계','',
      '- A=CPU 0, B=CPU 2, 제어=CPU 4, 외부 관찰=CPU 6. WSL2 vCPU 배치이며 물리 호스트 스케줄링과 주파수는 통제하지 못했다.',
      '- 같은 Rocky Linux 8.9 이미지와 GCC 8.5.0, 동일한 새 프로그램을 사용했다. 공식 소스에서 라이브러리도 새 경로에 빌드했다. 이미지 ID와 SHA, 빌드 옵션, 실제 환경은 artifacts.json에 있다.',
      '- 기본 정책 비교다. THP는 madvise이며 버전의 THP·purge 기본 정책을 완전히 같게 만든 비교는 아니다.',
      '- RSS는 worker가 멈춘 경계에서 외부 smaps_rollup으로 읽었다. 순간 최고값은 측정하지 못한다. 프로세스 VmHWM은 raw와 summary에 별도로 있다.',
      '- 데이터 검증은 별도 단계에서 전체 생존 바이트를 읽는다. 작업 비용에는 넣지 않았지만 뒤따르는 단계의 cache 상태에는 영향을 줄 수 있다.',
      '- 같은 객체 목록을 일괄 인계한다. 실제 서비스 큐, 동시 할당·해제, 다수 worker 경쟁, 다른 크기와 수명의 효과는 아직 관찰하지 않았다.',
      '- 세 번의 탐색 관찰이다. 숫자가 비슷하다고 동등성이 입증되는 것은 아니며, 작은 시간 차이는 우열로 표현하지 않는다.',
      '', '## 재현과 근거','',
      '[실행 절차](../observation/README.md), [새 계획](memory-behavior-plan.md), [전체 요약과 실행별 값](../experiments/memory-behavior-v1/summary.json), [빌드·환경](../experiments/memory-behavior-v1/artifacts.json), [원자료 해시](../experiments/memory-behavior-v1/raw-index.json).',
      '', '기존 실험 결과는 이 분석에 사용하지 않았다.']
    (ROOT/'docs/memory-behavior-report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print('Generated memory flow plots, cost tables, and descriptive report from 18 fresh runs.')

if __name__=='__main__':main()
