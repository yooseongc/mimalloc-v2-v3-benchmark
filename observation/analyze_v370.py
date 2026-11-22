"""Descriptive summaries of current-session measurements only."""
import collections
import hashlib
import importlib.util
import json
import pathlib
import statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=pathlib.Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/release-v370-v1'
RAW=ROOT/'results/release-v370-v1'
OUT=ROOT/'docs/v370'
VERSIONS=['v2.1.2','v3.5.0','v3.5.3','v3.6.0','v3.6.1','v3.7.0']
COLORS=['#64748b','#159895','#d58322','#6143b8','#d52c59','#0072b2']
MIB=2**20
STAGES=['baseline','allocate','write','free_half','free_rest','idle_5','reallocate','rewrite']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def desc(xs):return dict(median=statistics.median(xs),minimum=min(xs),maximum=max(xs),values=xs)
def load(p):return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8')
def fmt(d):return '{:.2f} [{:.2f}, {:.2f}]'.format(d['median'],d['minimum'],d['maximum'])
spec=importlib.util.spec_from_file_location('active_con_analysis',str(ROOT/'observation/analyze_concurrent.py'))
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    plan=load(EXP/'plan.json')
    for p,h in plan['hashes'].items():assert sha(ROOT/p)==h,p
    paths=list(RAW.rglob('*.json'))
    assert all(load(p)['valid'] for p in paths)
    concurrent=[load(p) for p in sorted((RAW/'concurrent/measured').glob('*.json'))]
    lifecycle=[load(p) for p in sorted((RAW/'lifecycle/measured').glob('*.json'))]
    collect=[load(p) for p in sorted((RAW/'lifecycle/collect').glob('*.json'))]
    assert len(concurrent)==126 and len(lifecycle)==36 and len(collect)==12
    assert [r['config'] for r in concurrent]==plan['concurrent']
    assert [r['entry'] for r in lifecycle]==plan['lifecycle']
    assert [r['entry'] for r in collect]==plan['collect']
    ca=load(EXP/'concurrent/artifacts.json');la=load(EXP/'lifecycle/artifacts.json')
    for r in concurrent:
        assert r['binary_sha256']==ca['binary']['sha256']
        assert r['library_sha256']==ca['libraries'][r['config']['version']]['sha256']
    for r in lifecycle+collect:assert r['library_sha256']==la['libraries'][r['version']]['sha256']
    cg=collections.defaultdict(list)
    for r in concurrent:cg[old.key(r)].append(old.metrics(r))
    cs=[]
    for (s,c,p,v),rows in sorted(cg.items()):
        assert len(rows)==3
        cs.append(dict(size=s,cap_mib=c,pairs=p,version=v,metrics={
            k:desc([r[k] for r in rows]) if all(r[k] is not None for r in rows) else None for k in rows[0]}))
    lg=collections.defaultdict(list)
    for r in lifecycle:
        p={p['name']:p for p in r['phases']};c={c['name']:c for c in r['checkpoints']}
        m=dict(first_use_ms=sum(p[s]['wall_ns'] for s in ('allocate','write'))/1e6,
            free_ms=sum(p[s]['wall_ns'] for s in ('free_half','free_rest'))/1e6,
            reuse_ms=sum(p[s]['wall_ns'] for s in ('reallocate','rewrite'))/1e6,
            process_hwm_mib=max(x['VmHWM'] for x in r['checkpoints'])/MIB,
            major_faults=sum(x['major_faults'] for x in r['phases']))
        for s in STAGES:
            m[s+'_rss_mib']=c[s]['Rss']/MIB
            m[s+'_thp_mib']=c[s]['AnonHugePages']/MIB
            if s in p:
                m[s+'_ms']=p[s]['wall_ns']/1e6
                m[s+'_cpu_ms']=p[s]['cpu_ns']/1e6
                m[s+'_minor_faults']=p[s]['minor_faults']
        lg[r['mode'],r['version']].append(m)
    ls=[]
    for (mode,v),rows in sorted(lg.items()):
        assert len(rows)==3
        ls.append(dict(mode=mode,version=v,metrics={k:desc([r[k] for r in rows]) for k in rows[0]}))
    col=[]
    for r in collect:
        p={p['name']:p for p in r['phases']};c={c['name']:c for c in r['checkpoints']}
        col.append(dict(version=r['version'],mode=r['mode'],
            before_rss_mib=c['free_rest']['Rss']/MIB,after_rss_mib=c['collect_force']['Rss']/MIB,
            idle_rss_mib=c['idle_5']['Rss']/MIB,collect_ms=p['collect_force']['wall_ns']/1e6,
            reuse_ms=sum(p[s]['wall_ns'] for s in ('reallocate','rewrite'))/1e6))
    stats=load(EXP/'stats/results.json');ss=[]
    assert len(stats)==32 and all(r['valid'] for r in stats)
    for r in stats:
        f=next(s for s in r['rows'] if s.get('stage')=='both_collected_again')
        ss.append(dict(version=r['version'],size=r['size'],merge=r['merge'],rep=r['rep'],
            A_free_bytes=f['A']['derived_freed_bytes'],B_free_bytes=f['B']['derived_freed_bytes'],
            parent_free_bytes=f['parent']['derived_freed_bytes'],current_bytes=f['sum']['current_bytes']))
    summary=dict(concurrent=cs,lifecycle=ls,collect=col,stats=ss,
        counts=dict(concurrent=126,lifecycle=36,collect=12,stats=32,smoke=36,pilot=42),
        plan_sha256=sha(EXP/'plan.json'),interpretation='3 independent runs per primary cell; median and range, no significance claim')
    control_paths=sorted((RAW/'reclaim-control').glob('*.json'))
    if control_paths:
        cp=load(EXP/'reclaim-control/plan.json')
        controls=[load(p) for p in control_paths]
        assert len(controls)==24 and [r['config'] for r in controls]==cp['order']
        gg=collections.defaultdict(list)
        for r in controls:
            c=r['config'];assert r['valid'] and r['ready']['page_reclaim_on_free']==c['reclaim']
            artifact=load(EXP/'reclaim-control'/c['version']/'artifacts.json')
            assert r['binary_sha256']==artifact['binary']['sha256']
            assert r['library_sha256']==artifact['libraries'][c['version']]['sha256']
            gg[c['version'],c['size'],c['reclaim']].append(old.metrics(r))
        summary['reclaim_control']=[dict(version=v,size=s,reclaim=opt,
            metrics={k:desc([r[k] for r in rs]) if all(r[k] is not None for r in rs) else None for k in rs[0]})
            for (v,s,opt),rs in sorted(gg.items())]
        summary['counts']['reclaim_control']=len(controls)
    native=EXP/'diagnostics/native-stats.json'
    if native.exists():
        summary['native_stats']=load(native)['records']
        summary['counts']['native_stats']=len(summary['native_stats'])
        summary['page_layout']=load(EXP/'diagnostics/page-layout.json')
        summary['counts']['page_layout']=1
    evidence={}
    for v,lib in la['libraries'].items():
        actual=ROOT/lib['path'].removeprefix('/work/')
        assert sha(actual)==lib['sha256']
        source=ROOT/('extern/mimalloc-'+v)
        flags=ROOT/'build/release-v370-v1/lifecycle'/v/'CMakeFiles/mimalloc.dir/flags.make'
        evidence[v]=dict(commit=lib['commit'],library_sha256=lib['sha256'],
            header_sha256=sha(source/'include/mimalloc.h'),compile_flags=flags.read_text())
    save(EXP/'build-evidence.json',evidence)
    save(EXP/'summary.json',summary)
    save(EXP/'raw-index.json',[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(paths)])
    diagnostic_paths=list((EXP/'stats').glob('*.jsonl'))+list((EXP/'diagnostics').glob('*.jsonl'))+[EXP/'diagnostics/page-layout.json']
    save(EXP/'diagnostic-index.json',[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(diagnostic_paths) if p.exists()])
    lines=['# v3.7.0 비교 전체 수치','', '중앙값 [최소, 최대]. 이번 실행의 여섯 버전만 비교한다. 각 기본 조건 3회.','',
        '## 동시 처리','', '| 객체 B | 상한 MiB | 쌍 | 버전 | 백만 완료 객체/s | worker CPU ns/객체 | 시작 RSS MiB | 종료 RSS MiB | 5초 RSS MiB | 중간 생존량 MiB |',
        '|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|']
    for r in cs:
        m=r['metrics'];keys=['mobjects_sec','worker_cpu_ns_object','ready_rss_mib','done_rss_mib','idle_rss_mib','middle_live_median_mib']
        lines.append('| {} | {} | {} | {} | {} |'.format(r['size'],r['cap_mib'],r['pairs'],r['version'],' | '.join(fmt(m[k]) if m[k] else 'unavailable' for k in keys)))
    lines += ['', '## 단계별 흐름 128 MiB','', '| 해제 | 버전 | 최초 할당+쓰기 ms | 해제 ms | 재할당+쓰기 ms | 쓰기 후 RSS MiB | 5초 RSS MiB |', '|---|---|---:|---:|---:|---:|---:|']
    for r in ls:
        m=r['metrics'];keys=['first_use_ms','free_ms','reuse_ms','write_rss_mib','idle_5_rss_mib']
        lines.append('| {} | {} | {} |'.format(r['mode'],r['version'],' | '.join(fmt(m[k]) for k in keys)))
    lines += ['', '## 별도 강제 수집 진단','', '조건당 1회. 성능 우열을 판정하는 반복 표본이 아니다.','',
        '| 해제 | 버전 | collect 이전 RSS MiB | 직후 RSS MiB | 5초 RSS MiB | collect ms | 재할당+쓰기 ms |','|---|---|---:|---:|---:|---:|---:|']
    for r in col:lines.append('| {} | {} | {} |'.format(r['mode'],r['version'],' | '.join('{:.2f}'.format(r[k]) for k in ('before_rss_mib','after_rss_mib','idle_rss_mib','collect_ms','reuse_ms'))))
    if 'reclaim_control' in summary:
        lines += ['', '## page_reclaim_on_free 단일 변수 진단','',
            '2쌍, 128 MiB. 같은 버전 안에서만 옵션을 바꾼 비교. 각 3회.','',
            '| 버전 | 크기 B | option | 백만 완료 객체/s | worker CPU ns/객체 | consumer CPU ns/객체 | 종료 RSS MiB |',
            '|---|---:|---:|---:|---:|---:|---:|']
        for r in summary['reclaim_control']:
            m=r['metrics']
            lines.append('| {} | {} | {} | {} |'.format(r['version'],r['size'],r['reclaim'],
                ' | '.join(fmt(m[k]) for k in ('mobjects_sec','worker_cpu_ns_object','consumer_cpu_ns_object','done_rss_mib'))))
    (OUT/'tables.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    cells=sorted(set((r['size'],r['cap_mib'],r['pairs']) for r in cs))
    fig,axes=plt.subplots(1,2,figsize=(13,5.5))
    for ax,key,title in zip(axes,['mobjects_sec','idle_rss_mib'],['Completed objects / second','RSS after 5 seconds idle']):
        for j,(v,color) in enumerate(zip(VERSIONS,COLORS)):
            points=[next(r['metrics'][key] for r in cs if (r['size'],r['cap_mib'],r['pairs'])==cell and r['version']==v) for cell in cells]
            x=[i+(j-2.5)*.14 for i in range(len(cells))]
            med=[p['median'] for p in points]
            ax.bar(x,med,width=.13,color=color,label=v,yerr=[[p['median']-p['minimum'] for p in points],[p['maximum']-p['median'] for p in points]],capsize=2)
        ax.set_xticks(range(len(cells)));ax.set_xticklabels(['{} B\n{} MiB\n{} pair(s)'.format(*cell) for cell in cells],fontsize=8)
        ax.set_title(title);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    axes[0].set_ylabel('Million objects/s');axes[1].set_ylabel('MiB');axes[0].legend(fontsize=8)
    fig.suptitle('mimalloc v3.7.0 follow-up | current-session runs, median and full range (n=3)')
    fig.tight_layout();fig.savefig(OUT/'concurrent.png',dpi=160);fig.savefig(OUT/'concurrent.svg');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),sharey=True)
    for ax,mode in zip(axes,['same','remote']):
        for v,color in zip(VERSIONS,COLORS):
            m=next(r['metrics'] for r in ls if r['mode']==mode and r['version']==v)
            ax.plot(range(len(STAGES)),[m[s+'_rss_mib']['median'] for s in STAGES],'o-',label=v,color=color)
        ax.plot(range(8),[0,128,128,64,0,0,128,128],'k--',label='Live requested bytes')
        ax.set_xticks(range(8));ax.set_xticklabels(['Start','Alloc','Write','Half free','All free','Idle 5s','Realloc','Rewrite'],rotation=30,ha='right')
        ax.set_title('A allocates / {} frees / A reuses'.format('A' if mode=='same' else 'B'));ax.grid(axis='y',alpha=.2);ax.set_ylim(bottom=0)
    axes[0].set_ylabel('Process RSS / live bytes (MiB)');axes[0].legend(fontsize=8)
    fig.suptitle('4 KiB objects, 128 MiB payload | median of 3 fresh processes; stage spacing is not time')
    fig.tight_layout();fig.savefig(OUT/'lifecycle.png',dpi=160);fig.savefig(OUT/'lifecycle.svg');plt.close(fig)
    print(json.dumps(summary['counts']))
    for cell in cells:
        vals={v:next(r['metrics']['mobjects_sec']['median'] for r in cs if (r['size'],r['cap_mib'],r['pairs'])==cell and r['version']==v) for v in VERSIONS}
        print(cell,vals,'v370/v361',vals['v3.7.0']/vals['v3.6.1'])
if __name__=='__main__':main()
