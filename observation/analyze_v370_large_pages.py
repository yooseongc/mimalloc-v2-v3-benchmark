"""Independent audit and descriptive tables for internal large-page A/B."""
import collections
import importlib.util
import json
import pathlib
import statistics

R=pathlib.Path(__file__).resolve().parents[1]
E=R/'experiments/v370-large-pages-v1'
O=R/'results/v370-large-pages-v1'
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
base=module('base',R/'observation/analyze_concurrent.py')
audit=module('audit',R/'observation/verify_v370.py')
load=audit.load;sha=base.sha;save=base.save
def main():
    p=load(E/'plan.json');a=load(E/'artifacts.json');prep=load(E/'preparation.json')
    assert sha(E/'preparation.json')==p['preparation_sha256']
    for f,h in dict(prep['hashes'],**p['pilot_hashes']).items():assert sha(R/f)==h,f
    for lib in a['libraries'].values():assert sha(audit.local_path(lib['path']))==lib['sha256']
    assert sha(audit.local_path(a['binary']['path']))==a['binary']['sha256']
    groups=collections.defaultdict(list);index=[];durations=[]
    for stage,n in [('smoke',12),('pilot',12),('measured',36)]:
        paths=sorted((O/stage).glob('*.json'));assert len(paths)==n
        for i,path in enumerate(paths):
            r=load(path);assert r['valid'] and r['exit_code']==0
            audit.audit_record(r,a)
            assert r['preparation_sha256']==sha(E/'preparation.json')
            assert r['ready']['purge_delay']==1000 and r['ready']['arena_purge_mult']==1 and r['ready']['purge_decommits']==1
            assert all(s['memory']['VmSwap']==0 for s in r['samples'])
            assert sorted(x[0] for x in r['thread_affinity'].values() if len(x)==1)==[0,2,4,6,8]
            if stage=='smoke':assert r['command'][-1]=='1'
            if stage=='measured':
                assert r['config']==p['order'][i] and r['plan_sha256']==sha(E/'plan.json')
                assert r['config']['objects']*r['config']['size']==p['total_bytes']
                m=base.metrics(r);t=m['seconds'];durations.append(t)
                m['middle_rss_mib']=statistics.median(s['memory']['VmRSS']/2**20 for s in r['samples'] if .1*t<s['progress']['elapsed_ns']/1e9<.9*t)
                groups[(r['config']['size'],r['config']['version'])].append(m)
            index.append(dict(path=path.relative_to(R).as_posix(),sha256=sha(path)))
    summary=[]
    for (size,v),ms in sorted(groups.items()):
        assert len(ms)==3
        summary.append(dict(size=size,profile=v,metrics={k:base.desc([m[k] for m in ms]) for k in ms[0]}))
    save(E/'summary.json',summary);save(E/'raw-index.json',index)
    save(E/'status.json',dict(status='Complete',counts=dict(smoke=12,pilot=12,measured=36),invalid=0,excluded=0,total_gib=p['total_bytes']/2**30,measured_seconds_range=[min(durations),max(durations)],major_faults=sum(m['major_faults'] for ms in groups.values() for m in ms),plan_sha256=sha(E/'plan.json')))
    lines=['# Large page A/B 수치','', '3회 중앙값 [최소–최대]. 처리량은 완료 payload이며 메모리 대역폭이 아니다.','', '| KiB | 프로필 | GiB/s | 작업 중 RSS MiB | 작업 중 생존량 MiB | minor fault |','|---:|---|---:|---:|---:|---:|']
    def fmt(d):return '{:.2f} [{:.2f}–{:.2f}]'.format(d['median'],d['minimum'],d['maximum'])
    for row in summary:lines.append('| {} | {} | {} |'.format(row['size']//1024,row['profile'],' | '.join(fmt(row['metrics'][k]) for k in ['gib_sec','middle_rss_mib','middle_live_median_mib','minor_faults'])))
    lines+=['','| KiB | 프로필 | 실행 초 | producer CPU ns/객체 | consumer CPU ns/객체 | idle RSS MiB |','|---:|---|---:|---:|---:|---:|']
    for row in summary:lines.append('| {} | {} | {} |'.format(row['size']//1024,row['profile'],' | '.join(fmt(row['metrics'][k]) for k in ['seconds','producer_cpu_ns_object','consumer_cpu_ns_object','idle_rss_mib'])))
    lines+=['','RSS/생존량은 실행 시간10–90% 샘플 중앙값. CPU에는 쓰기·검증·spin 대기가 포함된다.']
    (E/'tables.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    lookup={(r['size'],r['profile']):r['metrics'] for r in summary}
    fig,axes=base.plt.subplots(1,2,figsize=(10,4.5))
    sizes=[4096,16384,65536,262144]
    for ax,key,label in zip(axes,['gib_sec','middle_rss_mib'],['Completed payload (GiB/s)','Working RSS (MiB)']):
        for v,color in [('v361-default','#667085'),('v370-default','#cc5b20'),('v370-large','#087f8c')]:
            ds=[lookup[(s,v)][key] for s in sizes]
            ax.errorbar(range(4),[d['median'] for d in ds],yerr=[[d['median']-d['minimum'] for d in ds],[d['maximum']-d['median'] for d in ds]],label=v,color=color,marker='o',capsize=4)
        ax.set_xticks(range(4),['4','16','64','256']);ax.set_xlabel('Object size (KiB)');ax.set_ylabel(label)
        ax.set_ylim(bottom=0);ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    fig.suptitle('Internal large-page policy: fresh A/B, 2 producer/consumer pairs\nEqual {:.3f} GiB payload; median and range of 3 runs'.format(p['total_bytes']/2**30))
    fig.tight_layout();fig.savefig(E/'comparison.png',dpi=150);fig.savefig(E/'comparison.svg');base.plt.close(fig)
    print(json.dumps(load(E/'status.json'),indent=2))
    for row in summary:print(row['size']//1024,row['profile'],round(row['metrics']['gib_sec']['median'],3),round(row['metrics']['middle_rss_mib']['median'],3))
if __name__=='__main__':main()
