"""Verify frozen inputs and summarize every measured cell in the dev3 factorial."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
NS = 'dev3-20261122-v1'
EXP = ROOT/'experiments'/NS
RAW = ROOT/'results'/NS


def load(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plot(groups):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), layout='constrained')
    settings = ['OFF-0','OFF-1','ON-0','ON-1']
    for ax, metric, title, unit in zip(
            axes, ['GiB_s','idle_MiB'], ['Remote handoff throughput','RSS after 1 s idle'], ['GiB/s','MiB']):
        for dx,version,color,marker in [(-.09,'release','#396795','o'),(.09,'dev3','#a34328','s')]:
            for x,setting in enumerate(settings):
                values = [r[metric] for r in groups[version+'-'+setting,262144]]
                mid = median(values)
                ax.errorbar(x+dx,mid,yerr=[[mid-min(values)],[max(values)-mid]],color=color,
                            fmt=marker,capsize=4,label=version if x==0 else None)
        ax.set_xticks(range(4), ['OFF / 0','OFF / 1','ON / 0','ON / 1'])
        ax.set(xlabel='MI_SECURE / internal large pages', ylabel=unit, title=title, ylim=(0,None))
        ax.grid(axis='y',alpha=.25)
        ax.legend()
    fig.suptitle('256 KiB objects, two producer-consumer pairs | median and range of 3 runs')
    fig.savefig(EXP/'handoff-256k.png',dpi=160)
    plt.close(fig)


def main():
    plan = load(EXP/'plan.json')
    for name, expected in plan['hashes'].items():
        assert digest(ROOT/name) == expected, name
    rows = []
    for stage, count in [('smoke', 40), ('pilot', 24), ('measured', 120)]:
        paths = sorted((RAW/stage).glob('*.json'))
        assert len(paths) == count
        for i, path in enumerate(paths):
            record = load(path)
            assert record['valid']
            if stage != 'measured':
                continue
            rep, profile, case = record['entry']
            assert record['entry'] == plan['order'][i]
            points = {p['name']: p for p in record['checkpoints']}
            idle = next(p for k,p in points.items() if k.startswith('idle_') and float(k[5:]) == 1)
            row = dict(rep=rep, profile=profile, case=case, raw=path.name, sha256=digest(path),
                       peak_MiB=max(p['VmHWM'] for p in points.values())/2**20,
                       idle_MiB=idle['Rss']/2**20)
            if isinstance(case, int):
                cfg = record['config']
                total = cfg['objects']*cfg['size']
                assert total == plan['bytes_by_size'][str(case)]
                row['GiB_s'] = total/2**30/(record['final']['elapsed_ns']/1e9)
                row['post_MiB'] = points['done']['Rss']/2**20
            else:
                phases = {p['name']: p for p in record['phases']}
                row['free_ns_obj'] = sum(phases[k]['wall_ns'] for k in ['free_half','free_rest'])/record['object_count']
                row['post_MiB'] = points['free_rest']['Rss']/2**20
            rows.append(row)
    groups = defaultdict(list)
    for row in rows:
        groups[row['profile'], row['case']].append(row)
    assert len(groups)==40 and all(sorted(r['rep'] for r in rs)==[0,1,2] for rs in groups.values())
    (EXP/'metrics.json').write_text(json.dumps(rows, indent=2)+'\n', encoding='utf-8')
    lines = ['# 3회 반복 측정값', '', '처리량과 해제 시간은 중앙값 [최소, 최대], RSS는 중앙값(MiB)이다. 전체 반복별 값과 원시 파일 해시는 metrics.json에 있다.']
    for cases, metric, label in [([4096,65536,262144], 'GiB_s','처리량(GiB/s)'), (['same','remote'],'free_ns_obj','해제 시간(ns/객체)')]:
        lines.extend(['', '| 빌드 | 조건 | '+label+' | peak RSS | 해제 후 RSS | 1초 RSS |',
                      '|---|---|---:|---:|---:|---:|'])
        for case in cases:
            for profile in sorted({r['profile'] for r in rows}):
                group = groups[profile,case]
                v = [r[metric] for r in group]
                rss = [median(r[k] for r in group) for k in ['peak_MiB','post_MiB','idle_MiB']]
                desc = '{} KiB'.format(case//1024) if isinstance(case,int) else case
                lines.append('| {} | {} | {:.2f} [{:.2f}, {:.2f}] | {:.1f} | {:.1f} | {:.1f} |'.format(
                    profile,desc,median(v),min(v),max(v),*rss))
    (EXP/'tables.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    plot(groups)


if __name__ == '__main__':
    main()
