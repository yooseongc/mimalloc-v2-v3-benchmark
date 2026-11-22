"""Validate the frozen run set and regenerate tables/figures from immutable JSON."""
import hashlib,json,pathlib,statistics
ROOT=pathlib.Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/dev3-20261106-v1';OUT=ROOT/'results/dev3-20261106-v1';DOC=ROOT/'docs/dev3-20261106'
V=['v3.6.1','dev3-d6716d33'];MIB=2**20
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def local(p):return ROOT/p[len('/work/'):] if p.startswith('/work/') else pathlib.Path(p)
def stat(a):return dict(n=len(a),median=statistics.median(a),min=min(a),max=max(a))
def fmt(a):return '{:.3f} [{:.3f}, {:.3f}]'.format(a['median'],a['min'],a['max'])
def cp(r,n):return next(x for x in r['checkpoints'] if x['name']==n)
def phase(r,n):return next(x for x in r['phases'] if x['name']==n)
def load(family,stage,entries):
    paths=sorted((OUT/family/stage).glob('*.json'));assert len(paths)==len(entries),(family,stage,len(paths),len(entries))
    rows=[]
    for p,e in zip(paths,entries):
        r=read(p);assert r['valid'] and r['entry' if family=='lifecycle' else 'config']==e,p
        rows.append(r)
    return rows
def main():
    plan=read(EXP/'plan.json');assert plan['status']=='Frozen'
    for p,h in plan['hashes'].items():assert sha(ROOT/p)==h,p
    for family in ('lifecycle','concurrent','threads'):
        a=read(EXP/family/'artifacts.json')
        for lib in list(a['libraries'].values())+[a['binary']]:assert sha(local(lib['path']))==lib['sha256']
    c=load('concurrent','measured',plan['concurrent']);l=load('lifecycle','measured',plan['lifecycle'])
    t=load('threads','measured',plan['threads']);collect=load('lifecycle','collect',plan['collect'])
    allpaths=sorted(OUT.glob('*/*/*.json'));allrows=[read(p) for p in allpaths]
    assert len(allrows)==178,len(allrows)
    assert all(r['valid'] for r in allrows)
    DOC.mkdir(parents=True,exist_ok=True)
    summary=dict(frozen_at=plan['frozen_at'],plan_sha256=sha(EXP/'plan.json'),valid_raw=len(allrows),invalid_raw=0,
                 concurrent=[],lifecycle=[],threads=[],collect=[])
    tables=['# dev3 직접 측정 — 자동 생성 수치','',
      '모든 표는 중앙값 [최소, 최대]. 비율은 동일 반복의 dev3/v3.6.1 elapsed; 1보다 작으면 dev3가 빠름.',
      '기본 비교 각 버전 n=5. collect는 n=1이며 진단용. RSS는 프로세스 전체 값.',
      '', '## Remote-free 동시 처리', '',
      '|크기 / 쌍|v3.6.1 초|dev3 초|paired elapsed 비율|', '|---|---:|---:|---:|']
    for size in (64,1024,4096):
        for pairs in (1,2):
            rows=[r for r in c if r['config']['size']==size and r['config']['pairs']==pairs]
            d=dict(size=size,pairs=pairs,versions={})
            for v in V:
                rs=[r for r in rows if r['config']['version']==v]
                d['versions'][v]={k:stat([fn(r) for r in rs]) for k,fn in dict(
                  seconds=lambda r:r['final']['elapsed_ns']/1e9,cpu_seconds=lambda r:r['final']['cpu_ns']/1e9,
                  gib_per_second=lambda r:r['config']['objects']*size/(r['final']['elapsed_ns']/1e9)/2**30,
                  peak_mib=lambda r:max(x['VmHWM'] for x in r['checkpoints'])/MIB,
                  done_mib=lambda r:cp(r,'done')['Rss']/MIB,idle_mib=lambda r:r['checkpoints'][-1]['Rss']/MIB,
                  thp_done_mib=lambda r:cp(r,'done')['AnonHugePages']/MIB,
                  minor_faults=lambda r:cp(r,'done')['minor_faults']-cp(r,'ready')['minor_faults'],
                  major_faults=lambda r:cp(r,'done')['major_faults']-cp(r,'ready')['major_faults'],
                  waits=lambda r:sum(w['wait_polls'] for w in r['final']['workers'])).items()}
                d['objects']=rs[0]['config']['objects']
            pair=[]
            for rep in range(5):
                rs={r['config']['version']:r for r in rows if r['config']['rep']==rep}
                assert rs[V[0]]['config']['objects']==rs[V[1]]['config']['objects']
                pair.append(rs[V[1]]['final']['elapsed_ns']/rs[V[0]]['final']['elapsed_ns'])
            d['paired_elapsed_ratio']=stat(pair);summary['concurrent'].append(d)
            tables.append('|{} B / {}|{}|{}|{}|'.format(size,pairs,fmt(d['versions'][V[0]]['seconds']),fmt(d['versions'][V[1]]['seconds']),fmt(stat(pair))))
    tables+=['','### 동시 처리 메모리·CPU 중앙값','','|크기/쌍|버전|worker CPU 초|peak MiB|완료 MiB|idle 1초 MiB|완료 THP MiB|','|---|---|---:|---:|---:|---:|---:|']
    for d in summary['concurrent']:
        for v in V:
            a=d['versions'][v];tables.append('|{} / {}|{}|{}|'.format(d['size'],d['pairs'],v,'|'.join('{:.2f}'.format(a[k]['median']) for k in ('cpu_seconds','peak_mib','done_mib','idle_mib','thp_done_mib'))))
    tables+=['','## 128 MiB 메모리 수명','','|해제|버전|할당 ms|전체 해제 ms|재할당 ms|쓰기 후 RSS MiB|해제 후 RSS MiB|idle 5초 RSS MiB|','|---|---|---:|---:|---:|---:|---:|---:|']
    for mode in ('same','remote'):
        for v in V:
            rs=[r for r in l if r['version']==v and r['mode']==mode]
            d=dict(mode=mode,version=v)
            for name in ('allocate','write','free_half','free_rest','reallocate','rewrite'):
                d[name+'_ms']=stat([phase(r,name)['wall_ns']/1e6 for r in rs])
            d['free_total_ms']=stat([(phase(r,'free_half')['wall_ns']+phase(r,'free_rest')['wall_ns'])/1e6 for r in rs])
            for name in ('baseline','write','free_rest','idle_5','reallocate'):
                d[name+'_rss_mib']=stat([cp(r,name)['Rss']/MIB for r in rs])
            summary['lifecycle'].append(d)
            tables.append('|{}|{}|{}|'.format(mode,v,'|'.join(fmt(d[k]) for k in ('allocate_ms','free_total_ms','reallocate_ms','write_rss_mib','free_rest_rss_mib','idle_5_rss_mib'))))
    tables+=['','### 강제 collect 진단 (각 1회)','','|해제|버전|collect 전 MiB|collect 후 MiB|idle 5초 MiB|','|---|---|---:|---:|---:|']
    for r in collect:
        d=dict(mode=r['mode'],version=r['version'],before_mib=cp(r,'free_rest')['Rss']/MIB,after_mib=cp(r,'collect_force')['Rss']/MIB,idle_mib=cp(r,'idle_5')['Rss']/MIB)
        summary['collect'].append(d);tables.append('|{mode}|{version}|{before_mib:.2f}|{after_mib:.2f}|{idle_mib:.2f}|'.format(**d))
    tables+=['','## 스레드 생성·종료','','첫 malloc은 매 스레드의 첫 명시적 호출이며 pthread 내부 할당 이후일 수 있음. 두 번의 clock 호출 포함.',
       'empty 비용을 다른 결과에서 빼지 않음. 20000 cycle 상한으로 3초 목표보다 짧을 수 있음.','',
       '|조건|크기|v3.6.1 us/cycle|dev3 us/cycle|paired elapsed 비율|','|---|---:|---:|---:|---:|']
    for mode,size in [(0,64)]+[(m,s) for m in (1,2) for s in (64,4096)]:
        rows=[r for r in t if r['config']['mode']==mode and r['config']['size']==size]
        d=dict(mode=mode,size=size,versions={})
        for v in V:
            rs=[r for r in rows if r['config']['version']==v];d['cycles']=rs[0]['config']['cycles']
            d['versions'][v]={k:stat([fn(r) for r in rs]) for k,fn in dict(
               us_per_cycle=lambda r:r['final']['elapsed_ns']/r['config']['cycles']/1000,
               cpu_us_per_cycle=lambda r:r['final']['cpu_ns']/r['config']['cycles']/1000,
               first_malloc_ns=lambda r:r['final']['first_malloc_ns_sum']/r['config']['cycles'],
               peak_mib=lambda r:r['final']['peak_rss_bytes']/MIB,
               baseline_mib=lambda r:r['baseline']['Rss']/MIB,idle_mib=lambda r:r['idle']['Rss']/MIB,
               minor_faults=lambda r:r['final']['minor_faults'],major_faults=lambda r:r['final']['major_faults']).items()}
        ratios=[]
        for rep in range(5):
            rs={r['config']['version']:r for r in rows if r['config']['rep']==rep}
            assert rs[V[0]]['config']['cycles']==rs[V[1]]['config']['cycles']
            ratios.append(rs[V[1]]['final']['elapsed_ns']/rs[V[0]]['final']['elapsed_ns'])
        d['paired_elapsed_ratio']=stat(ratios);summary['threads'].append(d)
        tables.append('|{}|{}|{}|{}|{}|'.format(('empty','local','remote_exit')[mode],size,fmt(d['versions'][V[0]]['us_per_cycle']),fmt(d['versions'][V[1]]['us_per_cycle']),fmt(stat(ratios))))
    tables+=['','### 스레드 보조 지표','','|조건/크기|버전|첫 malloc ns|CPU us/cycle|peak MiB|idle MiB|','|---|---|---:|---:|---:|---:|']
    for d in summary['threads']:
        for v in V:
            a=d['versions'][v];tables.append('|{}/{}|{}|{}|'.format(('empty','local','remote_exit')[d['mode']],d['size'],v,'|'.join(fmt(a[k]) for k in ('first_malloc_ns','cpu_us_per_cycle','peak_mib','idle_mib'))))
    (DOC/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    (DOC/'tables.md').write_text('\n'.join(tables)+'\n',encoding='utf-8')
    (EXP/'verification.json').write_text(json.dumps(dict(status='pass',raw_count=len(allrows),measured=130,collect=4,
        raw_hashes={str(p.relative_to(ROOT)):sha(p) for p in allpaths},analysis_sha256=sha(pathlib.Path(__file__))),indent=2)+'\n',encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for ax,key,title in zip(axs,('concurrent','threads'),('Remote-free batch pipeline','Thread creation / teardown')):
        ds=summary[key]
        labels=['{} B / {} pair'.format(d['size'],d['pairs']) if key=='concurrent' else '{} / {} B'.format(('empty','local','remote exit')[d['mode']],d['size']) for d in ds]
        med=[d['paired_elapsed_ratio']['median'] for d in ds]
        lo=[m-d['paired_elapsed_ratio']['min'] for m,d in zip(med,ds)]
        hi=[d['paired_elapsed_ratio']['max']-m for m,d in zip(med,ds)]
        ax.errorbar(med,range(len(ds)),xerr=[lo,hi],fmt='o',capsize=4)
        ax.set_yticks(range(len(ds)),labels);ax.axvline(1,color='gray',linestyle='--');ax.set_xlim(left=0)
        ax.set_title(title);ax.set_xlabel('dev3 / v3.6.1 elapsed (lower is faster)');ax.grid(axis='x',alpha=.2)
    fig.suptitle('Pinned dev3 d6716d33: paired median and min-max, n=5')
    fig.savefig(DOC/'elapsed-ratios.png',dpi=160);plt.close(fig)
    print('Verified {} raw records; wrote {}'.format(len(allrows),DOC))
if __name__=='__main__':main()
