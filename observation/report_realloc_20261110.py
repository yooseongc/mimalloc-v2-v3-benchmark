"""Post-measurement report and static figure; does not modify frozen inputs."""
import json, pathlib, statistics, hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/realloc-20261110-v1'
OUT=ROOT/'results/realloc-20261110-v1'
s=json.loads((EXP/'summary.json').read_text())
plan=json.loads((EXP/'plan.json').read_text())
art=json.loads((EXP/'artifacts.json').read_text())
assert s['valid_runs']==360
for p,h in plan['hashes'].items():
    assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
for p,h in s['raw_hashes'].items():
    assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
versions=['before','strict','tail'];colors=['#64748b','#d97706','#087f8c']
def pick(api,size,f,v):return next(x for x in s['cells'] if (x['api'],x['size'],x['fraction'],x['version'])==(api,size,f,v))
def med(x,key):return x[key]['median']

fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
fig.suptitle('realloc: shrink by 25% | 128 MiB initial payload',fontsize=17,fontweight='bold')
for row,size in enumerate([4096,8*2**20]):
    xs=[pick(0,size,12,v) for v in versions]
    ax=axes[row,0];vals=[med(x,'ns_per_call') for x in xs]
    ax.bar(versions,vals,color=colors,width=.58)
    ax.set_yscale('log');ax.set_ylabel('ns per realloc (log scale)');ax.set_title(('4 KiB' if row==0 else '8 MiB')+' blocks: cost')
    ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    for i,y in enumerate(vals):ax.text(i,y*1.15,'{:,.1f}'.format(y),ha='center',fontsize=11)
    ax.set_ylim(min(vals)/2,max(vals)*3)
    ax=axes[row,1];positions=np.arange(3);w=.22
    for j,k in enumerate(['shrunk','idle','collected']):
        vals=[x['rss_mib'][k]['median'] for x in xs]
        ax.bar(positions+(j-1)*w,vals,w,label={'shrunk':'After shrink','idle':'Idle 1 s','collected':'Forced collect'}[k],color=['#93c5fd','#3b82f6','#1e3a8a'][j])
    ax.set_xticks(positions,versions);ax.set_ylabel('Process RSS (MiB)');ax.set_title(('4 KiB' if row==0 else '8 MiB')+' blocks: RSS')
    ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True);ax.set_ylim(0,210);ax.legend(fontsize=8,ncol=3,loc='upper center')
    if row==1:
        lazy=xs[2]['lazy_free_mib']['idle']['median']
        ax.text(.03,.04,'tail: {:.2f} MiB LazyFree remains in RSS'.format(lazy),transform=ax.transAxes,fontsize=10,bbox=dict(facecolor='white',alpha=.9,edgecolor='none'))
fig.supxlabel('Medians of 5 fresh processes per condition. Cost uses repeated batches; RSS uses separate processes.\nHuge fast-path timings are very short; do not interpret small timing ratios.',fontsize=10)
fig.savefig(EXP/'realloc-comparison.png',dpi=170);fig.savefig(EXP/'realloc-comparison.svg');plt.close(fig)

rows=[json.loads(p.read_text()) for p in OUT.glob('measured/*.json')]
cost=[r for r in rows if not r['config']['life']]
life=[r for r in rows if r['config']['life']]
for r in rows:
    c=r['config']
    stays=(c['fraction']==15 or (c['fraction']==12 and (c['version']=='before' or (c['version']=='tail' and c['size']==8*2**20))))
    assert r['done']['moved']==(0 if stays else r['done']['calls']),c
    assert r['valid'] and r['exit_code']==0
text=['# realloc 축소 변경 직접 측정 보고서','',
      'Execution status: Completed. Experiment: realloc-20261110-v1.','',
      '## realloc을 쉽게 설명하면','',
      '`malloc`은 보관함을 새로 빌리고, `realloc`은 이미 빌린 보관함의 크기를 바꾸는 요청이다. '
      '기존 보관함을 계속 쓸 수도 있고, 새 보관함으로 내용물을 옮긴 뒤 이전 것을 반납할 수도 있다. '
      '작게 줄여 달라고 해도 복사를 아끼려고 큰 보관함을 유지할 수 있다. 이번 변경은 이 허용 범위를 '
      '50%에서 12.5%로 줄였고, 큰 할당에는 뒤쪽을 OS가 회수할 수 있게 표시하는 예외를 추가했다.','',
      'RSS는 프로세스가 현재 RAM에 올려 둔 페이지 양이다. 요청 크기, allocator usable size, RSS, '
      'LazyFree는 서로 다른 지표다. LazyFree는 RSS에서 즉시 빠진 바이트가 아니다.','',
      '## 비교 범위와 실행 환경','',
      '|이름|고정 commit|의미|','|---|---|---|']
for v,meaning in zip(versions,['축소 기준 변경 직전','12.5% 기준만 적용','huge tail reset까지 적용']):
    commit=art['libraries'][v]['commit'];text.append('|{}|[{}](https://github.com/microsoft/mimalloc/commit/{})|{}|'.format(v,commit[:8],commit,meaning))
text += ['',
    '세 대상에는 same-heap 검사가 모두 들어 있다. 따라서 이 결과는 heap 이동 오류 수정의 비용 비교가 아니다. '
    '이번 결과를 기존 d6716d33 또는 v3.6.1 실험과 합치지 않았다.','',
    '- AMD Ryzen 7 5700X, x86-64, WSL2 Linux 6.6.87.2, Rocky Linux 8, GCC 8.5.0, glibc 2.28.',
    '- 이미지 `'+art['image']+'`.',
    '- CPU0 worker / CPU2 controller, cpuset 0,2 및 node0, 4GiB limit, swap 금지, CPU quota 없음, network none.',
    '- Release -O3 -DNDEBUG, MI_SECURE/MTE/PAC OFF, 같은 실행파일과 LD_PRELOAD, 런타임 정책 upstream-default.',
    '- THP '+art['environment']['thp']+'. 실제 AnonHugePages는 raw와 summary에 별도 기록.',
    '- host 부하·주파수·기존 상주 컨테이너는 미통제. NUMA 메모리 정책은 cpuset-mems만 사용.','',
    '2 APIs × 2 크기 × 3 축소 비율 × 3 버전 × 5회 × 2 측정 방식 = **360 valid runs**. '
    '추가 smoke36/pilot36/preflight3 통과. 각 프로세스는 요청량128MiB를 전체 쓰기한 뒤 축소한다. '
    '새 크기는 실제 usable size의 15/16, 3/4, 1/4이다. 정렬 API는 64바이트 정렬이다.','',
    '비용은 warmup1 후 고정 배치 수로 반복한 realloc loop 시간 합/calls이다. 할당·memset·검증·free는 '
    '비용 timed region 밖이며, timer/loop/포인터 배열 대입 비용은 포함된다. '
    'RSS는 별도 fresh process의 단발 축소에서 측정하며 비용 반복의 메모리 상태와 합치지 않는다.','',
    '## 대표 결과: 25% 축소, 일반 realloc','',
    '중앙값이며 대괄호는 5회 최소–최대. RSS 단위는 MiB, 프로세스 전체 값이다.','',
    '|블록|버전|ns/call [min–max]|이동 비율|usable 합계|축소 직후 RSS|1초 후 RSS|강제 회수 RSS|LazyFree (1초)|',
    '|---|---|---:|---:|---:|---:|---:|---:|---:|']
for size in [4096,8*2**20]:
    for v in versions:
        x=pick(0,size,12,v);t=x['ns_per_call']
        text.append('|{}|{}|{:.1f} [{:.1f}–{:.1f}]|{:.0f}%|{:.2f}|{:.2f}|{:.2f}|{:.2f}|{:.2f}|'.format('4KiB' if size==4096 else '8MiB',v,t['median'],t['min'],t['max'],100*med(x,'moved_fraction'),med(x,'usable_mib'),*[x['rss_mib'][k]['median'] for k in ['shrunk','idle','collected']],x['lazy_free_mib']['idle']['median']))
text += ['', '![realloc comparison](../experiments/realloc-20261110-v1/realloc-comparison.png)','',
    '## 해석','',
    '4KiB의 25% 축소에서 before는 원래 블록을 유지하고 strict/tail은 모두 새 블록으로 이동했다. '
    '이로 인해 복사·새 할당·해제 비용이 추가됐다. usable 합계는 줄었지만 축소 직후와 idle1초 RSS는 '
    '오히려 커졌다. 강제 collect 뒤에는 새 버전 RSS가 낮아졌다. 빈 allocator 페이지가 OS에 '
    '즉시 반환되지 않는 것과 일치하는 관찰이며, 단순 idle이 자동 회수를 보장하지 않았다.','',
    '8MiB의 25% 축소에서 strict는 이동하지만 tail은 포인터와 usable size를 유지한다. '
    'tail에서 LazyFree 증가를 관찰했고 RSS는 바로 줄지 않았다. Linux 구현은 `_mi_os_reset`에서 '
    '`_mi_prim_reset`을 호출하고 MADV_FREE를 우선 시도한다. 따라서 이전 설명의 “반환”은 '
    '이 환경에서는 즉시 RSS 감소가 아니라 OS가 필요할 때 회수할 수 있도록 표시하는 의미다. '
    '압박을 가해서 실제 reclaim시키는 실험은 수행하지 않았다.','',
    '6.25% 축소는 일반 작은 블록에서 기존 유지 경로를 확인하는 대조군이다. '
    '큰 블록에서는 tail 버전이 이 작은 축소에도 reset을 시도하므로 이전의 거의 무비용 경로에 '
    '추가 비용이 발생할 수 있다. 75% 축소는 세 버전 모두 복사 경로를 확인하는 대조군이다. '
    '정렬 API 결과는 별도 전체 표에 있으며 일반 API와 합산하지 않았다.','',
    '정렬 API의 4KiB→3KiB에서는 새 요청 합계가96MiB여도 strict/tail의 usable 합계는112MiB였다. '
    '일반 API의96MiB와 다르다. 이는 정렬과 size class를 고려해야 함을 보여 주며, 12.5% 기준을 '
    '모든 정렬 할당의 최종 낭비율 상한으로 해석하면 안 된다.','',
    '## 전체 결과와 변동성','',
    (EXP/'summary.md').read_text(encoding='utf-8').split('\n',2)[2],
    '### 동일 반복끼리의 비용 비율','',
    '|API|블록|남긴 비율|비교|median|min|max|','|---|---:|---:|---|---:|---:|---:|']
for x in s['paired_ratios']:
    a,z,f=x['cell'];r=x['ratio'];text.append('|{}|{}|{}/16|{}/{}|{:.3f}|{:.3f}|{:.3f}|'.format('aligned' if a else 'realloc',z,f,x['numerator'],x['denominator'],r['median'],r['min'],r['max']))
text += ['', '### 측정 한계','',
    '- 누적 realloc timed region은 {:.6f}–{:.3f}ms였다. 특히 huge 유지 경로는 타이머/루프 비용의 영향이 크므로 작은 ns 차이 또는 비율을 성능 개선으로 단정하지 않는다.'.format(min(r['done']['wall_ns'] for r in cost)/1e6,max(r['done']['wall_ns'] for r in cost)/1e6),
    '- 본 측정의 비용 배치 수는 조건별 {}–{}로 동결했다. 모든 버전은 같은 조건에서 동일한 작업량이다. 1초 목표는 준비/쓰기 포함 pilot loop의 보정 목표이며 realloc 자체를 1초 측정했다는 뜻이 아니다.'.format(min(r['config']['cycles'] for r in cost),max(r['config']['cycles'] for r in cost)),
    '- lifecycle의 축소 직후는 retained prefix 검증 직후이다. tail 영역을 다시 touch하지 않았다. RSS checkpoint와 transient VmHWM은 구분했다.',
    '- 강제 mi_collect(true)는 별도 진단이며 정상 idle 결과로 취급하지 않는다. 작은 변화의 통계적 유의성/서비스 전체 처리량/모든 크기 및 heap 이동에 일반화하지 않는다.',
    '- 5회 중앙값/min/max와 paired 비율을 제공한다. outlier를 제거하지 않았고 신뢰구간/p99/perf counters는 산출하지 않았다.',
    '- allocator 경로/hash/version, payload 보존, 정렬, checksum/calls/live0, affinity, swap, throttling, OOM counters 검증 통과. 실패/제외 run 없음. raw stderr와 cgroup 기록 보존.','',
    '## 재현과 산출물','',
    '- 설계: [realloc-20261110-plan.md](realloc-20261110-plan.md).',
    '- Frozen at: '+plan['frozen_at']+'. Design revision: plan.json SHA256 `'+hashlib.sha256((EXP/'plan.json').read_bytes()).hexdigest()+'`.',
    '- 고정 계약: `experiments/realloc-20261110-v1/plan.json`; 빌드·환경·소스: `artifacts.json`.',
    '- 집계: 같은 디렉터리 `summary.json`, `summary.md`; 전체 raw: `results/realloc-20261110-v1/`.',
    '- 실행: `observation/realloc_20261110/run.ps1`. 최초 source cache는 공식 upstream clone이 필요하다. 기존 frozen namespace가 있으면 새 namespace를 만들어 재실행한다.',
    '- 최초 준비 명령: `git clone --no-checkout https://github.com/microsoft/mimalloc.git extern/mimalloc-dev3-realloc-20261110-cache`. 그 후 PowerShell에서 `./observation/realloc_20261110/run.ps1`을 실행한다. 소스 다운로드는 측정 전에 끝내며 빌드/측정은 network none이다.',
    '- 보고서/그림 재생성: `python observation/report_realloc_20261110.py` (matplotlib 필요).',
    '- upstream 배경: [issue1488](https://github.com/microsoft/mimalloc/issues/1488).','']
(ROOT/'docs/realloc-20261110-report.md').write_text('\n'.join(text),encoding='utf-8')
print('Verified frozen inputs and 360 raw hashes; wrote report and figure.')
