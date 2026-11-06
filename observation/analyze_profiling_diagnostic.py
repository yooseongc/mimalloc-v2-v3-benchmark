"""Validate retained diagnostic records and summarize without external packages."""
import collections
import hashlib
import json
import pathlib
import re
import statistics
import subprocess

ROOT=pathlib.Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/profiling-diagnostic-v1'
OUT=ROOT/'results/profiling-diagnostic-v1'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def resolve(p): return ROOT/p.removeprefix('/work/') if hasattr(str,'removeprefix') else ROOT/p[len('/work/'):]
plan=json.loads((EXP/'plan.json').read_text())
for p,h in plan['hashes'].items(): assert sha(ROOT/p)==h,p
for stage,expected in [('smoke',16),('pilot',4)]:
    paths=list((OUT/stage).glob('*/result.json'))
    assert len(paths)==expected
    assert all(json.loads(p.read_text())['valid'] for p in paths)
records=[];groups=collections.defaultdict(list);details=[]
pattern=re.compile(r'^\s*(\d+):\s*(\d+)\s*\[\s*(\d+):\s*(\d+)\]\s*@\s*(.*)$')
for i,cfg in enumerate(plan['runs']):
    p=OUT/'measured'/('{:03d}'.format(i))/'result.json'
    r=json.loads(p.read_text());assert r['valid'] and r['config']==cfg
    for f in r['profiles']:
        fp=resolve(f['path']); assert sha(fp)==f['sha256']
        lines=fp.read_text().splitlines()
        head=pattern.match(lines[0].replace('heap profile:',''))
        assert head and int(head[3])>0
        rows=[]
        for line in lines[1:]:
            m=pattern.match(line)
            if m: rows.append(dict(inuse_count=int(m[1]),inuse_bytes=int(m[2]),alloc_count=int(m[3]),alloc_bytes=int(m[4]),stack=m[5].split()))
        assert sum(x['alloc_count'] for x in rows)==int(head[3])
        # Snapshot free updates may race the header/body: do not assert live totals equality.
        if f==r['profiles'][-1]:
            details.append(dict(run=i,config=cfg,totals=list(map(int,head.groups()[:4])),rows=rows))
    groups[(cfg['version'],cfg['size'],cfg['mode'])].append(r)
    records.append(r)
summary=[]
for key,rs in sorted(groups.items()):
    assert len(rs)==3
    rates=[r['config']['objects']/(r['final']['elapsed_ns']/1e9)/1e6 for r in rs]
    row=dict(version=key[0],size=key[1],mode=key[2],n=3,mops=statistics.median(rates),mops_range=[min(rates),max(rates)],
        elapsed=statistics.median(r['final']['elapsed_ns']/1e9 for r in rs),
        cpu_seconds=statistics.median(r['final']['cpu_ns']/1e9 for r in rs),
        peak_mib=statistics.median(max(x['VmHWM'] for x in r['checkpoints'])/2**20 for r in rs),
        snapshots=[len(r['profiles']) for r in rs],profile_bytes=sum(f['bytes'] for r in rs for f in r['profiles']))
    base=groups[(key[0],key[1],'off')]
    paired=[r['final']['elapsed_ns']/next(b['final']['elapsed_ns'] for b in base if b['config']['rep']==r['config']['rep'])-1 for r in rs]
    row['paired_elapsed_change_pct']=statistics.median(paired)*100
    row['paired_elapsed_change_range_pct']=[min(paired)*100,max(paired)*100]
    summary.append(row)
addresses=sorted({a for d in details for r in d['rows'] for a in r['stack'] if 0x400000<=int(a,16)<0x403000})
binary=ROOT/'build/release-v361-v1/concurrent/concurrent'
symbols={}
for a in addresses:
    symbols[a]=subprocess.check_output(['addr2line','-f','-C','-e',str(binary),a],universal_newlines=True).strip()
for d in details:
    for r in d['rows']:
        r['benchmark_frames']=[symbols[a] for a in r['stack'] if a in symbols]
data=dict(summary=summary,profiles=details,symbols=symbols,valid_measured=len(records),
    profile_files=sum(len(r['profiles']) for r in records))
(EXP/'summary.json').write_text(json.dumps(data,indent=2)+'\n')
(EXP/'status.json').write_text(json.dumps(dict(design='Frozen',smoke='Pass',pilot='Pass',
    measured='Complete',valid_measured=len(records),invalid=0,profile_files=data['profile_files'],
    plan_sha256=sha(EXP/'plan.json'),analysis_sha256=sha(pathlib.Path(__file__))),indent=2)+'\n')
lines=['# Profiling 진단 결과','', '2026-11-01. Design status: Frozen. Execution status: Complete.', '',
       '기존 결과는 보존했다. v3.6.0/v3.6.1, 2쌍, 128 MiB 상한, 기본 concurrent workload를 새로 비교했다.',
       '16회 smoke, 4회 짧은 OFF pilot, 60회 본 진단. 조건당 3회이며 통계적 유의성을 주장하지 않는다.',
       '기존 실행파일과 라이브러리를 재사용하고 매 실행 hash/loader/affinity/checksum/생존량/swap/throttling을 검증했다.', '',
       '## 처리량과 진단 비용','',
       'M객체/s는 중앙값 [최소–최대]. 시간 변화는 같은 반복 블록의 OFF 대비 elapsed 증가율 중앙값이다.',
       'sample512/sample4m은 종료 시에만 출력한다. periodic512는 512 KiB 샘플링 + 1 GiB 할당 간격 text 출력이다.', '',
       '|버전|크기 B|조건|M객체/s|OFF 대비 시간 %|worker CPU s|관측 peak MiB|출력 파일 수(각 반복)|',
       '|---|---:|---|---:|---:|---:|---:|---|']
find=lambda v,s,m: next(x for x in summary if (x['version'],x['size'],x['mode'])==(v,s,m))
findings=['## 주요 발견','',
    '이번 짧은 진단에서 heap profiling은 기대한 producer 할당 경로와 해제 추적을 보여줬지만, 기존 속도 저하의 CPU 원인은 밝혀내지 못했다.',
    'OFF 처리량 중앙값 기준 v3.6.1/v3.6.0 차이는 1 KiB {:+.1f}%, 4 KiB {:+.1f}%였다. 1 KiB 반복 범위는 겹친다. 과거 14% 차이를 같은 크기로 재현하지 못했으며 과거 결과를 무효화하지 않는다.'.format(*[(find('v3.6.1',s,'off')['mops']/find('v3.6.0',s,'off')['mops']-1)*100 for s in (1024,4096)]),
    'v3.6.1 1 KiB에서 512 KiB 샘플링/종료 출력은 paired elapsed 중앙값 +12.7% [10.7–28.6%], 4 MiB는 +0.4% [-2.5–14.9%], 주기 text 출력은 +25.2% [21.9–39.2%]였다. 일반 운영 오버헤드의 보장값이 아니다.',
    '4 KiB ON 결과는 변동과 객체 레이아웃 변화 영향으로 OFF보다 빠른 중앙값도 있다. 음수 시간 차이를 profiling 최적화 효과로 해석하지 않는다.',
    'reclaim1 및 stats512 단독 변경에서 일관된 회귀 해소 증거는 얻지 못했다. 세 번의 짧은 관찰로 해당 정책의 영향을 배제하지 않는다.',
    'v3.6.1 sample512의 최종 프로파일 6개에서 producer 경로 sampled live bytes는 모두 0이었다. 남은 sampled 304 B 한 객체는 std::thread 생성 경로였다. 이를 workload 누수로 분류하지 않는다.',
    '주기 출력은 실행마다 104–114개 파일을 생성했다. 요청한 1 GiB 간격은 구현의 근사 트리거이며 정확한 workload 바이트당 파일 수가 아니다.',
    '따라서 후속 원인 분석은 더 긴 OFF 재현과 CPU profiling이 우선이다. heap profiling은 이번 단순 workload보다 다양한 할당 경로를 가진 실제 응용에서 더 많은 정보를 줄 가능성이 있다.', '']
lines[8:8]=findings
for r in summary:
    lines.append('|{}|{}|{}|{:.2f} [{:.2f}–{:.2f}]|{:+.1f}|{:.2f}|{:.2f}|{}|'.format(r['version'],r['size'],r['mode'],r['mops'],*r['mops_range'],r['paired_elapsed_change_pct'],r['cpu_seconds'],r['peak_mib'],r['snapshots']))
lines += ['', '## プロファイル検証'.replace('プロファイル検証','프로파일 검증'), '',
    '{}개 profile 파일의 SHA와 sampled allocation 수를 검증했다. 마지막 스냅샷의 호출 경로와 raw sampled totals는 experiments/profiling-diagnostic-v1/summary.json에 있다.'.format(data['profile_files']),
    '프로파일의 바이트/객체 수는 샘플 원자료이며 전체 workload 할당량으로 간주하지 않는다. 주기 스냅샷은 누적값이므로 합산하지 않는다.',
    '주소는 기존 바이너리의 addr2line으로 함수명까지 해석했다. 디버그 정보가 없어 소스 줄 번호는 미확인이다.', '',
    '## 한계와 재현','',
    'perf cycles probe는 No permission to enable cycles event로 실패했다. CPU hot spot은 측정하지 못했다.',
    '공식 기본 protobuf 대신 text를 사용했다. sampling은 객체 레이아웃과 스케줄링도 바꾸므로 ON 결과로 OFF 회귀의 원인을 단정하지 않는다.',
    'RSS는 작업/idle 중 관측이며 종료 스냅샷의 메모리 피크는 포함하지 않을 수 있다. p99와 실제 서비스 비용은 미측정이다.',
    'pilot은 작업량 조정을 위한 짧은 실행이다. 2초 목표와 실제 시간 차이, WSL2 및 host 부하 영향을 고려해야 한다.',
    '동결 문서의 512-object batch 표현은 오류다. 실제 재사용 소스는 batch=256이고 두 쌍의 총 객체 수를 512 배수로 맞췄다. 동결 문서는 보존하며 이 정정은 구현이나 작업량 변경이 아니다.',
    '컨테이너: 기존 고정 Rocky 이미지, network none, cpuset 0,2,4,6,8,10, cpuset-mems 0. 명령: python3 observation/profiling_diagnostic.py prepare 후 measured, python3 observation/analyze_profiling_diagnostic.py.',
    'prepare는 기존 namespace가 있으면 거부한다. measured는 검증된 완료 실행을 건너뛴다. 새 실험은 별도 namespace를 사용한다.', '']
(ROOT/'docs/profiling-diagnostic-report.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps(summary,indent=2))
