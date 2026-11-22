"""Generate v3.7.0 release report from newly audited measurements only."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(p): return json.loads((ROOT/p).read_text(encoding='utf-8'))
def fmt(d): return '{:.2f} [{:.2f}–{:.2f}]'.format(d['median'],d['minimum'],d['maximum'])
def pair(rows, **where):
    return [next(r['metrics'] for r in rows if r['version']==v and all(r[k]==x for k,x in where.items())) for v in ('v3.6.1','v3.7.0')]
def main():
    status=load('experiments/release-v370-v1/status.json')
    assert status['status']=='Complete'
    s=load('experiments/release-v370-v1/summary.json')
    purge=load('experiments/purge-delay-v370-v1/summary.json')
    sizes=load('experiments/allocation-size-v370-v1/summary.json')
    plan=load('experiments/release-v370-v1/plan.json')
    sizeplan=load('experiments/allocation-size-v370-v1/plan.json')
    artifacts=load('experiments/release-v370-v1/lifecycle/artifacts.json')
    env=artifacts['environment']
    total=sum(sum(stages.values()) for stages in status['counts'].values())+status['stats']
    lines=['# mimalloc v3.7.0 처리 비용과 메모리 비교','',
        '2026-11-18. Execution status: Complete. Design status: Frozen.',
        '식별자: release-v370-v1 / purge-delay-v370-v1 / allocation-size-v370-v1.',
        'Frozen at (UTC): '+plan['frozen_at'],
        'Design revision (plan SHA-256): `'+status['plan_sha256']+'`.','',
        '## 범위와 판정','',
        '기존 다섯 릴리스에 v3.7.0을 추가해 여섯 버전을 모두 새로 빌드·측정했다. '
        '과거 표본은 합치지 않았다. 기본 조건당 3회이며 수치는 중앙값 [최소–최대]다. '
        '작은 차이의 통계적 유의성·동등성이나 실제 응용의 우열을 판정하지 않는다.',
        '처리량은 할당·전체 쓰기·큐 인계·양끝 내용 확인·해제·대기를 포함한다. '
        'smoke는 전체 payload를 확인한다. 순수 malloc/free 호출 비용이나 DRAM 대역폭 수치가 아니다.',
        '총 {}개 fresh-process 기록을 검증했다. invalid={}, excluded={}. '
        '기본 동시 처리126, lifecycle36, 강제 collect12, stats32, purge36, 크기72회이며 '
        '나머지는 smoke/default78, pilot66회다.'.format(total,status['invalid'],status['excluded']),'',
        '## 직전 릴리스 대비 기본 동시 처리','',
        '변화율은 v3.7.0 / v3.6.1 처리량 중앙값 − 1이다. 양수면 처리량 증가다. '
        'RSS는 객체 해제가 끝난 뒤 5초 값이며 생존 요청량과 다르다.','',
        '| 크기 B | 상한 MiB | 쌍 | v3.6.1 M객체/s | v3.7.0 M객체/s | 변화 | v3.6.1 idle RSS MiB | v3.7.0 idle RSS MiB |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|']
    cells=sorted({(r['size'],r['cap_mib'],r['pairs']) for r in s['concurrent']})
    for size,cap,pairs in cells:
        a,b=pair(s['concurrent'],size=size,cap_mib=cap,pairs=pairs)
        change=100*(b['mobjects_sec']['median']/a['mobjects_sec']['median']-1)
        lines.append('| {} | {} | {} | {} | {} | {:+.1f}% | {} | {} |'.format(size,cap,pairs,fmt(a['mobjects_sec']),fmt(b['mobjects_sec']),change,fmt(a['idle_rss_mib']),fmt(b['idle_rss_mib'])))
    lines+=['','![동시 처리](v370/concurrent.png)','','[여섯 버전 전체 수치](v370/tables.md). '
        '반복 범위가 겹치는 차이는 확정적인 개선·회귀로 해석하지 않는다. '
        '버전 비교만으로 purge 수정, 보안 내부 구조, 통계 경로 각각의 인과 효과를 분리할 수 없다.','',
        '## 기준 버전별 처리량 비율','',
        'v3.7.0 중앙값 / 각 기준 버전 중앙값. 동일 환경·동일 작업량의 이번 실행만 사용한다.','',
        '| 크기 B | 상한 MiB | 쌍 | /v2.1.2 | /v3.5.0 | /v3.5.3 | /v3.6.0 | /v3.6.1 |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|']
    for size,cap,pairs in cells:
        rs={r['version']:r['metrics']['mobjects_sec']['median'] for r in s['concurrent'] if (r['size'],r['cap_mib'],r['pairs'])==(size,cap,pairs)}
        lines.append('| {} | {} | {} | {} |'.format(size,cap,pairs,' | '.join('{:.3f}'.format(rs['v3.7.0']/rs[v]) for v in ('v2.1.2','v3.5.0','v3.5.3','v3.6.0','v3.6.1'))))
    lines+=['','## 동일/다른 스레드 해제와 메모리 수명','',
        '4 KiB × 32768개, 요청량128 MiB. A가 할당·쓰기하고 A 또는 B가 해제한 뒤 A가 새로 할당한다. '
        '이 재할당 단계는 realloc API가 아니다. 강제 collect는 별도 조건당 1회 진단이다.','',
        '| 해제 담당 | 버전 | 해제 ms | 쓰기 후 RSS MiB | 전부 해제 후 5초 RSS MiB | 재할당+쓰기 ms |',
        '|---|---|---:|---:|---:|---:|']
    for r in s['lifecycle']:
        if r['version'] in ('v3.6.1','v3.7.0'):
            lines.append('| {} | {} | {} |'.format(r['mode'],r['version'],' | '.join(fmt(r['metrics'][k]) for k in ('free_ms','write_rss_mib','idle_5_rss_mib','reuse_ms'))))
    lines+=['','![lifecycle](v370/lifecycle.png)','','![작업 중 RSS와 생존량](v370/memory-1k.png)','',
        'RSS 잔류만으로 누수를 판단할 수 없다. 관찰 시 worker는 살아 있고 idle만으로 purge가 반드시 실행되지는 않는다. '
        '진행 카운터의 생존량은 비동기 샘플의 추정치다.','',
        '## purge 대기시간 정렬','',
        '1 KiB, 2쌍, 128 MiB 상한. purge_delay=10/1000 ms와 arena_purge_mult=1만 정렬했다. '
        '완전히 동일한 정책 또는 purge 수정 단독 효과 비교가 아니다.','',
        '| delay ms | 버전 | 작업 중 RSS MiB | 완료 RSS MiB | 5초 RSS MiB | M객체/s |',
        '|---:|---|---:|---:|---:|---:|']
    for r in purge:
        if r['version'] in ('v3.6.1','v3.7.0'):
            lines.append('| {} | {} | {} |'.format(r['delay_ms'],r['version'],' | '.join(fmt(r['metrics'][k]) for k in ('middle_rss_mib','done_rss_mib','idle_rss_mib','mobjects_sec'))))
    lines+=['','![purge](purge-delay-v370/rss.png)','','[purge 전체 수치](purge-delay-v370/tables.md).',
        '', '## 동일 총 바이트의 할당 크기 비교','',
        '모든 조건 {:.3f} GiB, 2쌍, 128 MiB 상한, 256 KiB 인계 배치, delay1000/mult1. '
        '처음 준비 적재한 0.125 GiB의 쓰기는 timed region 밖이다.'.format(sizeplan['total_bytes']/2**30),'',
        '| 객체 KiB | v3.6.1 GiB/s | v3.7.0 GiB/s | 변화 | v3.6.1 작업 중 RSS MiB | v3.7.0 작업 중 RSS MiB |',
        '|---:|---:|---:|---:|---:|---:|']
    for size in (4096,16384,65536,262144):
        a,b=pair(sizes,size=size)
        lines.append('| {} | {} | {} | {:+.1f}% | {} | {} |'.format(size//1024,fmt(a['gib_sec']),fmt(b['gib_sec']),100*(b['gib_sec']['median']/a['gib_sec']['median']-1),fmt(a['middle_rss_mib']),fmt(b['middle_rss_mib'])))
    lines+=['','![크기](allocation-size-v370/size-sweep.png)','','[크기 전체 수치](allocation-size-v370/tables.md).','',
        '## 통계 API 진단','',
        '각 조건2회. A가1000개 할당하고 B가 해제한 실제 호출 수와 allocator 통계의 귀속을 구분한다. '
        '최종 합계 current_bytes=0을 검증했다. 아래는 첫 반복의 명시적 collect 후 값이며 전체 반복은 summary.json에 있다.','',
        '| 버전 | 객체 B | 자동 병합 | A 귀속 해제 B | B 귀속 해제 B | parent 귀속 해제 B |',
        '|---|---:|---:|---:|---:|---:|']
    for r in s['stats']:
        if r['rep']==0:
            lines.append('| {} | {} | {} | {} | {} | {} |'.format(*(r[k] for k in ('version','size','merge','A_free_bytes','B_free_bytes','parent_free_bytes'))))
    lines+=['','## 환경과 재현 증거','',
        '- '+env['rocky'], '- CPU: '+next(x.split(':',1)[1].strip() for x in env['cpu'].splitlines() if x.startswith('Model name:'))+'.', '- 커널: `'+env['kernel']+'`.',
        '- 컴파일러: '+env['compiler'].splitlines()[0]+'. glibc: '+env['glibc'].splitlines()[0]+'.',
        '- 이미지: `'+artifacts['image_id']+'`.',
        '- cpuset 0,2,4,6,8,10 / NUMA node0 / 6 GiB 상한 / swap 금지 / CPU quota 없음 / network none.',
        '- THP: `'+env['thp']+'`. 실제 AnonHugePages는 raw와 집계에 별도 기록.',
        '- 공통 Release -O3 -DNDEBUG, MI_SECURE=OFF. 캐시·컴파일 플래그·실제 library hash는 build-evidence.json 및 artifacts.json.',
        '', '| 버전 | 고정 커밋 |', '|---|---|']
    for v,lib in artifacts['libraries'].items():lines.append('| {} | `{}` |'.format(v,lib['commit']))
    lines+=['',
        '본 동시 처리 구간은 {:.3f}–{:.3f}초, 관찰한 최대 process HWM은 {:.2f} MiB다. '
        '본 동시 처리 major fault 합계는 {}다.'.format(*status['measured_concurrent_seconds_range'],status['process_peak_rss_mib'],status['measured_concurrent_major_faults']),
        '', '검증: allocator 버전·경로·hash, 공통 바이너리, thread affinity, checksum·처리 개수·최종 생존량0, '
        'swap0·throttling 미증가, 동결 문서/실행기/pilot hash, raw 개수·실행 순서. '
        '원시 데이터는 results/{release,purge-delay,allocation-size}-v370-v1, '
        '계획·manifest·집계·상태는 experiments/동일 namespace에 보존한다.',
        '', '재현 명령은 [RELEASE_V370](../observation/RELEASE_V370.md)을 따른다. '
        '이미 동결된 namespace에서 build/prepare/freeze를 반복하지 않는다. '
        '분석·그래프·검증·보고서는 기존 raw로 재생성할 수 있다.',
        '', '## 한계와 미실행 항목','',
        'WSL2 가상화, Windows host 부하·주파수·온도는 통제하지 않았다. cpuset-mems는 '
        '컨테이너 허용 node를 제한하며 별도 mbind 정책 실험은 아니다. '
        '각3회는 탐색 관찰이며 신뢰구간·p99·perf counter·실제 서비스 성능을 제공하지 않는다. '
        '짧은 pilot은 작업량 보정용이고 최종 성능 표본이 아니다.',
        '하드웨어 MTE/PAC, 보안 방어 효과, realloc API, thread churn, CPython/Rust/macOS 기능은 '
        '이번 matrix에서 실행하지 않았다. [소스 변경점](v370-source-notes.md), '
        '[코드 비교](v370-code-analysis.md), [기존 realloc 원인 분리 진단](realloc-20261110-report.md), '
        '[기존 dev3 비교](dev3-20261106-report.md)는 별도 근거다. '
        '기본 버전 차이를 특정 커밋이나 수정의 단독 효과로 단정하지 않는다.','']
    a,b=pair(s['concurrent'],size=4096,cap_mib=128,pairs=2)
    c,d=pair(s['concurrent'],size=4096,cap_mib=512,pairs=2)
    pa,pb=pair(purge,delay_ms=10)
    sa,sb=pair(sizes,size=4096)
    za,zb=pair(sizes,size=262144)
    assert a['seconds']['maximum'] < b['seconds']['minimum']
    assert c['seconds']['maximum'] < d['seconds']['minimum']
    stats_by_version={v:{(r['size'],r['merge'],r['rep']):(r['A_free_bytes'],r['B_free_bytes'],r['parent_free_bytes'],r['current_bytes']) for r in s['stats'] if r['version']==v} for v in ('v3.6.1','v3.7.0')}
    assert stats_by_version['v3.6.1']==stats_by_version['v3.7.0']
    findings=['## 주요 관찰','',
        'v3.7.0이 모든 조건에서 개선되지는 않았다. 기본 4 KiB·2쌍 처리량 중앙값은 '
        'v3.6.1 대비 128 MiB 상한에서 {:+.1f}%, 512 MiB 상한에서 {:+.1f}%였다. '
        '세 반복에서는 두 조건 모두 v3.7.0의 처리 시간이 더 긴 범위에 있었다. '
        '이 조건을 업그레이드 시 우선 회귀 점검 대상으로 삼는다.'.format(
            100*(b['mobjects_sec']['median']/a['mobjects_sec']['median']-1),
            100*(d['mobjects_sec']['median']/c['mobjects_sec']['median']-1)),
        '반면 1 KiB·2쌍, purge_delay=10 ms, arena_purge_mult=1에서는 '
        '5초 RSS 중앙값이 {:.2f}→{:.2f} MiB였다. '
        '작업 중 생존량 추정 중앙값도 {:.2f}→{:.2f} MiB로 달랐다. '
        '기본 정책과 다른 결과이며, RSS 차이를 순수 반환 효율 개선이나 purge 수정 단독 효과로 해석하지 않는다.'.format(
            pa['idle_rss_mib']['median'],pb['idle_rss_mib']['median'],
            pa['middle_live_median_mib']['median'],pb['middle_live_median_mib']['median']),
        '수명 관찰에서는 두 버전 모두 128 MiB payload를 해제한 뒤에도 약143 MiB RSS가 '
        '5초간 유지됐다. 통계 API의 해제량 귀속도 두 버전에서 같은 패턴이었다. '
        '따라서 메모리 반환·스레드 통계가 전반적으로 달라졌다고 볼 수는 없다.',
        '같은 총 바이트·256 KiB 인계 배치의 별도 크기 비교에서 4 KiB 처리량 변화는 '
        '{:+.1f}%였다. 기본 비교와 배치·purge 정책이 다르므로 수치를 합치지 않는다.'.format(
            100*(sb['gib_sec']['median']/sa['gib_sec']['median']-1)),
        '같은 크기 비교의 256 KiB에서는 {:.2f}→{:.2f} GiB/s, {:+.1f}%였다. '
        '이 조건도 우선 회귀 점검 대상으로 삼는다. 작업 중 RSS 중앙값은 {:.2f}→{:.2f} MiB였다.'.format(
            za['gib_sec']['median'],zb['gib_sec']['median'],
            100*(zb['gib_sec']['median']/za['gib_sec']['median']-1),
            za['middle_rss_mib']['median'],zb['middle_rss_mib']['median']),
        '각 조건3회의 탐색 관찰이다. 배포 판단에는 실제 응용의 객체 크기·수명·해제 스레드 '
        '구성과 기능 수정 필요성을 함께 고려해야 한다.','']
    findings=[item for line in findings for item in ([line,''] if line else [])]
    at=lines.index('## 범위와 판정');lines[at:at]=findings
    (ROOT/'docs/v370-report.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Generated docs/v370-report.md from {} verified runs'.format(total))
if __name__=='__main__':main()
