"""Regenerate security profile tables and plots from frozen raw observations."""
import hashlib,json,pathlib,statistics
ROOT=pathlib.Path(__file__).resolve().parents[1];EXP=ROOT/'experiments/security-20261106-v1';OUT=ROOT/'results/security-20261106-v1';DOC=ROOT/'docs/security-20261106'
PROFILES=['OFF','MINIMAL','CHECKED','ON','FULL','CHECKED_PAC_WEAK'];MIB=2**20
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stat(a):return dict(n=len(a),median=statistics.median(a),min=min(a),max=max(a))
def fmt(a):return '{:.3f} [{:.3f}, {:.3f}]'.format(a['median'],a['min'],a['max'])
def cp(r,n):return next(x for x in r['checkpoints'] if x['name']==n)
def phase(r,n):return next(x for x in r['phases'] if x['name']==n)
def mapped(p):return ROOT/p[len('/work/'):] if p.startswith('/work/') else pathlib.Path(p)
def main():
    plan=load(EXP/'plan.json');assert plan['status']=='Frozen'
    for p,h in plan['hashes'].items():assert sha(ROOT/p)==h,p
    for f in ('threads','concurrent','lifecycle'):
        a=load(EXP/f/'artifacts.json')
        for x in [a['binary']]+list(a['libraries'].values()):assert sha(mapped(x['path']))==x['sha256']
    modes=load(EXP/'mode-validation.json');assert len(modes)==6 and all(x['valid'] for x in modes.values())
    allpaths=sorted(OUT.glob('*/*/*.json'));assert len(allpaths)==192,len(allpaths)
    assert all(load(p)['valid'] for p in allpaths)
    data={}
    for family in ('local','concurrent','lifecycle'):
        paths=sorted((OUT/family/'measured').glob('*.json'));assert len(paths)==len(plan[family])
        data[family]=[load(p) for p in paths]
        for r,e in zip(data[family],plan[family]):assert r['entry' if family=='lifecycle' else 'config']==e
    summary=dict(frozen_at=plan['frozen_at'],plan_sha256=sha(EXP/'plan.json'),valid_workloads=192,mode_validations=6,cells=[],lifecycle=[])
    table=['# 보안 모드 성능: 자동 생성 수치','','모든 수치는 중앙값 [최소, 최대]. 성능 n=5, lifecycle n=3.',
      'paired 비율은 같은 반복의 profile/OFF. 1보다 크면 시간이 더 걸림. PAC 추가 비용은 CHECKED 기준으로 별도 계산.',
      'local은 first/last 접근, concurrent는 전체 쓰기 및 queue 인계를 포함하므로 두 시나리오의 절대 비용을 직접 비교하지 않음.']
    for family in ('local','concurrent'):
        for size in (64,4096):
            rows=[r for r in data[family] if r['config']['size']==size]
            index={(r['config']['version'],r['config']['rep']):r for r in rows}
            d=dict(family=family,size=size,profiles={})
            table+=['','## {} / {} B'.format(family,size),'','|모드|elapsed 초|paired /OFF|CPU 초|peak MiB|idle RSS MiB|','|---|---:|---:|---:|---:|---:|']
            for v in PROFILES:
                rs=[index[v,i] for i in range(5)]
                key='cycles' if family=='local' else 'objects'
                for i,r in enumerate(rs):assert r['config'][key]==index['OFF',i]['config'][key]
                def metrics(r):
                    f=r['final'];n=r['config'][key]*(1024 if family=='local' else 1)
                    if family=='local':
                        peak=f['peak_rss_bytes'];idle=r['idle'];faults=f['minor_faults'];maj=f['major_faults']
                    else:
                        peak=max(x['VmHWM'] for x in r['checkpoints']);idle=r['checkpoints'][-1]
                        faults=cp(r,'done')['minor_faults']-cp(r,'ready')['minor_faults'];maj=cp(r,'done')['major_faults']-cp(r,'ready')['major_faults']
                    return dict(seconds=f['elapsed_ns']/1e9,cpu_seconds=f['cpu_ns']/1e9,ns_per_object=f['elapsed_ns']/n,
                        peak_mib=peak/MIB,idle_mib=idle['Rss']/MIB,thp_idle_mib=idle['AnonHugePages']/MIB,minor_faults=faults,major_faults=maj)
                ms=[metrics(r) for r in rs];a={k:stat([x[k] for x in ms]) for k in ms[0]}
                a['work_count']=rs[0]['config'][key];a['work_unit']=key
                a['paired_elapsed_ratio']=stat([index[v,i]['final']['elapsed_ns']/index['OFF',i]['final']['elapsed_ns'] for i in range(5)])
                a['paired_cpu_ratio']=stat([index[v,i]['final']['cpu_ns']/index['OFF',i]['final']['cpu_ns'] for i in range(5)])
                d['profiles'][v]=a
                table.append('|{}|{}|{}|{}|{}|{}|'.format(v,fmt(a['seconds']),fmt(a['paired_elapsed_ratio']),fmt(a['cpu_seconds']),fmt(a['peak_mib']),fmt(a['idle_mib'])))
            d['pac_increment_elapsed']=stat([index['CHECKED_PAC_WEAK',i]['final']['elapsed_ns']/index['CHECKED',i]['final']['elapsed_ns'] for i in range(5)])
            table+=['','PAC=WEAK / CHECKED elapsed: **{}**.'.format(fmt(d['pac_increment_elapsed']))]
            summary['cells'].append(d)
    table+=['','## 128 MiB lifecycle: 동일 스레드 해제','','|모드|할당 ms|free 합계 ms|재할당 ms|쓰기후 RSS MiB|해제후 RSS MiB|idle 1초 RSS MiB|','|---|---:|---:|---:|---:|---:|---:|']
    for v in PROFILES:
        rs=[r for r in data['lifecycle'] if r['version']==v];assert len(rs)==3
        a=dict(profile=v)
        for name in ('allocate','write','reallocate','rewrite'):
            a[name+'_ms']=stat([phase(r,name)['wall_ns']/1e6 for r in rs])
        a['free_ms']=stat([(phase(r,'free_half')['wall_ns']+phase(r,'free_rest')['wall_ns'])/1e6 for r in rs])
        for name in ('baseline','write','free_rest','idle_1'):
            a[name+'_rss_mib']=stat([cp(r,name)['Rss']/MIB for r in rs])
        summary['lifecycle'].append(a)
        table.append('|{}|{}|'.format(v,'|'.join(fmt(a[k]) for k in ('allocate_ms','free_ms','reallocate_ms','write_rss_mib','free_rest_rss_mib','idle_1_rss_mib'))))
    DOC.mkdir(parents=True,exist_ok=True)
    (DOC/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    (DOC/'tables.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    labels=['MINIMAL','CHECKED','ON','FULL','CHECKED + PAC WEAK']
    for ax,d in zip(axs.flat,summary['cells']):
        stats=[d['profiles'][v]['paired_elapsed_ratio'] for v in PROFILES[1:]];med=[x['median'] for x in stats]
        ax.barh(labels,med,color=['#327f9e','#4e9c9b','#e0a24a','#c45d55','#7874ad'],alpha=.85)
        ax.errorbar(med,range(5),xerr=[[x['median']-x['min'] for x in stats],[x['max']-x['median'] for x in stats]],fmt='none',color='black',capsize=3)
        top=max(x['max'] for x in stats)
        for i,x in enumerate(med):ax.text(stats[i]['max']+.02*top,i,'{:.2f}x'.format(x),va='center',fontsize=9)
        ax.set_xlim(0,top*1.23);ax.axvline(1,color='gray',linestyle='--')
        ax.set_title('{} / {} B'.format(d['family'],d['size']));ax.set_xlabel('elapsed / OFF (lower is faster)');ax.grid(axis='x',alpha=.2)
    fig.suptitle('dev3 d6716d33 security cost: paired median and min-max, n=5')
    fig.savefig(DOC/'security-cost.png',dpi=160);plt.close(fig)
    verification=dict(status='pass',valid_workloads=192,mode_validations=6,analysis_sha256=sha(pathlib.Path(__file__)),raw_hashes={str(p.relative_to(ROOT)):sha(p) for p in allpaths})
    diagnostic=EXP/'syscall-diagnostic/results.json'
    if diagnostic.exists():
        rows=load(diagnostic);assert len(rows)==4 and all(r['valid'] and r['exit_code']==0 for r in rows)
        sizes=load(EXP/'syscall-diagnostic/good-sizes.json');assert set(sizes)==set(PROFILES)
        assert all(r['version']==30602 for r in sizes.values())
        verification['diagnostic_hashes']={str(p.relative_to(ROOT)):sha(p) for p in sorted((EXP/'syscall-diagnostic').glob('*')) if p.is_file()}
        verification['syscall_diagnostics']=4;verification['size_class_queries']=6
    (EXP/'verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
    print('Verified 192 workloads + 6 mode validations; generated tables and chart')
if __name__=='__main__':main()
