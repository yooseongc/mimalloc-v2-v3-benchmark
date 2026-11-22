"""Generate reviewable tables/report solely from audited current-session data."""
import json
import pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
def load(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def fmt(d):return '{:.2f} [{:.2f}–{:.2f}]'.format(d['median'],d['minimum'],d['maximum'])
def main():
    status=load('experiments/release-v361-v1/status.json')
    assert status['status']=='Complete'
    s=load('experiments/release-v361-v1/summary.json')
    for r in s['stats']:
        assert r['current_bytes']==0
        if r['merge']==0:
            assert (r['A_free_bytes'],r['B_free_bytes'])==((64000,0) if r['size']==64 else (163840,3932160))
    p=load('experiments/purge-delay-v361-v1/summary.json')
    z=load('experiments/allocation-size-v361-v1/summary.json')
    plan=load('experiments/release-v361-v1/plan.json')
    sizeplan=load('experiments/allocation-size-v361-v1/plan.json')
    def metric(size,pairs,v):
        return next(r['metrics'] for r in s['concurrent'] if r['size']==size and r['pairs']==pairs and r['cap_mib']==128 and r['version']==v)
    small0=metric(1024,2,'v3.6.0');small1=metric(1024,2,'v3.6.1')
    sizes={r['size']:r['metrics'] for r in z if r['version']=='v3.6.1'}
    lines=['# mimalloc v3.6.1 처리 비용과 메모리 비교','',
        '2026-10-31. Execution status: Complete. Design status: Frozen.',
        '식별자: release-v361-v1 / purge-delay-v361-v1 / allocation-size-v361-v1.',
        '기본 계획 동결 시각(UTC): '+plan['frozen_at']+'.',
        'Design revision (plan SHA-256): `'+status['plan_sha256']+'`.','',
        '## 주요 발견과 판단','',
        '이번 조건에서 v3.6.1은 v3.6.0 대비 일괄적인 처리량 개선을 보이지 않았다. '
        '기본 1 KiB·2쌍 처리량은 {:.2f}→{:.2f} M객체/s, {:.1f}% 감소했고 '
        'idle RSS 중앙값은 {:.2f}→{:.2f} MiB였다. '
        '속도 저하와 함께 큰 메모리 절감이 나타난 조건은 아니다.'.format(
            small0['mobjects_sec']['median'],small1['mobjects_sec']['median'],
            100*(1-small1['mobjects_sec']['median']/small0['mobjects_sec']['median']),
            small0['idle_rss_mib']['median'],small1['idle_rss_mib']['median']),
        '기본 4 KiB 조건에서 v3.6.1의 처리량 중앙값은 약 4–6% 낮았다. '
        '별도 동일 바이트/256 KiB 인계 비교에서는 4 KiB가 약 11% 낮았고, '
        '16/64/256 KiB 차이는 각각 약 -2%/+3%/+1%였다. 서로 다른 배치와 정책의 수치를 합치지 않는다.',
        'v3.6.1 안에서 4→16/64 KiB로 묶으면 완료 바이트 처리량이 각각 {:.2f}/{:.2f}배였다. '
        '64→256 KiB의 추가 이득은 작고 반복 범위가 겹쳤다. '
        '이 효과에는 객체 수 감소·쓰기·큐 전달·실제 생존량 차이가 포함된다.'.format(
            sizes[16384]['gib_sec']['median']/sizes[4096]['gib_sec']['median'],
            sizes[65536]['gib_sec']['median']/sizes[4096]['gib_sec']['median']),
        'purge delay1000/mult1에서는 v3.6.1의 idle RSS 중앙값이 더 낮았지만 '
        '작업 중 RSS는 비슷했다. 종료 시점이 반환 주기의 어느 위치인지도 영향을 주므로 '
        'idle 값만으로 전반적인 메모리 효율 개선을 주장하지 않는다.',
        '성능만을 이유로 v3.6.0에서 일괄 전환할 근거는 이번 관찰에서 부족하다. '
        '전환 검증에서는 1 KiB·2쌍과 4 KiB 흐름을 우선 회귀 조건으로 삼는 것이 적절하다. '
        '기능 수정의 필요성은 실제 사용 API와 별도로 판단해야 한다. '
        '원인 분리가 필요하면 page_reclaim_on_free와 stats_merge_threshold를 각각 통제하는 '
        '새 진단이 다음 단계이며, 이번 보고서의 완료 범위에는 포함하지 않는다.','',
        '## 범위와 읽는 법','',
        'v2.1.2/v3.5.0/v3.5.3/v3.6.0/v3.6.1을 같은 환경에서 새로 빌드하고 측정했다. '
        '과거 측정값을 새 표본에 섞지 않았다. 각 본 측정 조건은 3회이며 표는 중앙값 [최소–최대]다. '
        '처리량은 할당·전체 쓰기·인계·내용 확인·해제를 합친 비용이다.',
        '기본 동시 처리 105회, lifecycle 30회, 강제 collect 진단 10회, stats 24회, '
        'purge 본 측정 30회, 크기 본 측정 60회를 완료했다. smoke/default 검증 65회와 pilot 55회도 완료했다. '
        '총 379개 fresh-process 관찰이며 invalid/excluded는 0이다.','',
        '## 환경과 소스','',
        'AMD Ryzen 7 5700X, 8코어/16 논리 CPU, WSL2 Linux 6.6.87.2, '
        'Rocky Linux 8.9, GCC 8.5.0, glibc 2.28. 컨테이너 cpuset 0,2,4,6,8,10, '
        'NUMA node 0, CPU quota와 memory limit은 max, network none. '
        '빌드 시 VM 메모리 약 31.3 GiB, available 약 29.5 GiB. THP는 madvise, HugeTLB 예약은 0이다.',
        '고정 이미지: `sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877`. '
        'Release -O3 -DNDEBUG, MI_SECURE=OFF. 실제 로드 버전·경로·SHA를 매 실행 검증했다.',
        'v3.6.1 commit: `56dc5eb80145f9a3ba7ca23d47c6a248b9d8586c`. '
        '전체 소스 SHA·명령·CMake cache·library/header hash는 '
        '[빌드 기록](../experiments/release-v361-v1/lifecycle/artifacts.json)과 '
        '[소스 기록](../experiments/release-v361-v1/sources.json)에 있다.','',
        '## v3.6.0과의 기본 동작 비교','',
        '처리량 비율은 v3.6.1/v3.6.0으로 1보다 크면 이 흐름에서 더 빠르다. '
        '범위 비중첩은 기술적 관찰이며 유의성 검정이 아니다. RSS는 작업 종료 후 worker를 살려 둔 5초 시점이다.','',
        '| 객체 / 상한 / 쌍 | v3.6.0 M객체/s | v3.6.1 M객체/s | 비율 | v3.6.0 idle MiB | v3.6.1 idle MiB |',
        '|---|---:|---:|---:|---:|---:|']
    ratios=[]
    for r in s['concurrent']:
        if r['version']!='v3.6.1':continue
        prev=next(x for x in s['concurrent'] if x['version']=='v3.6.0' and all(x[k]==r[k] for k in ('size','cap_mib','pairs')))
        a,b=prev['metrics'],r['metrics'];ratio=b['mobjects_sec']['median']/a['mobjects_sec']['median']
        ratios.append(dict(size=r['size'],cap_mib=r['cap_mib'],pairs=r['pairs'],ratio=ratio))
        lines.append('| {} B / {} MiB / {} | {} | {} | {:.3f} | {} | {} |'.format(
            r['size'],r['cap_mib'],r['pairs'],fmt(a['mobjects_sec']),fmt(b['mobjects_sec']),ratio,fmt(a['idle_rss_mib']),fmt(b['idle_rss_mib'])))
    lines+=['','![동시 처리](v361/concurrent.png)','', '![1 KiB RSS와 생존량](v361/memory-1k.png)','',
        '전체 다섯 버전의 CPU 비용·생존량·RSS와 단계별 수치는 [전체 표](v361/tables.md)에 있다. '
        '공간 상한은 실제 생존량이나 RSS와 같지 않다.','',
        '## 동일 스레드/다른 스레드 해제','',
        '4 KiB × 32768개, 128 MiB를 할당·쓰기·절반/전체 해제·5초 idle·재사용했다. '
        'same은 A 할당/A 해제, remote는 A 할당/B 해제이며 재사용은 A가 한다.','',
        '| 버전 | 해제 | 최초 할당+쓰기 ms | 해제 ms | 재할당+쓰기 ms | 5초 RSS MiB |',
        '|---|---|---:|---:|---:|---:|']
    for r in s['lifecycle']:
        if r['version'] in ('v3.6.0','v3.6.1'):
            lines.append('| {} | {} | {} |'.format(r['version'],r['mode'],' | '.join(fmt(r['metrics'][k]) for k in ('first_use_ms','free_ms','reuse_ms','idle_5_rss_mib'))))
    lines+=['','![단계 흐름](v361/lifecycle.png)','',
        '강제 collect는 별도 1회 진단이다. idle과 섞지 않으며 '
        '[전체 표](v361/tables.md)에 전후 RSS와 재사용 비용을 기록했다.','',
        '## purge 대기시간 비교','',
        '1 KiB, 2쌍, 128 MiB 상한. delay 10/1000 ms, arena_purge_mult=1. '
        '다른 정책은 각 버전 기본값이므로 완전한 동일 정책 비교가 아니다.','',
        '| delay ms | 버전 | M객체/s | 작업 중 RSS MiB | idle 5초 RSS MiB |',
        '|---:|---|---:|---:|---:|']
    for r in p:
        if r['version'] in ('v3.6.0','v3.6.1'):
            lines.append('| {} | {} | {} |'.format(r['delay_ms'],r['version'],' | '.join(fmt(r['metrics'][k]) for k in ('mobjects_sec','middle_rss_mib','idle_rss_mib'))))
    lines+=['','[다섯 버전 purge 전체 표](purge-delay-v361/tables.md). '
        '작업 중 RSS는 각 실행의 10–90% 시간대 샘플 중앙값을 다시 3회 요약한 것이다.','',
        '## 할당 크기 비교','',
        '2쌍, 128 MiB 상한, 256 KiB 인계 배치, delay1000/mult1. '
        '모든 크기/버전에서 완료 payload {:.3f} GiB를 동일하게 처리했다. '
        '초기 128 MiB는 timed 쓰기 밖에 있다. GiB/s는 완료 요청 바이트 기준이며 DRAM 대역폭 계측값이 아니다.'.format(sizeplan['total_bytes']/2**30),'',
        '| 객체 KiB | v3.6.0 GiB/s | v3.6.1 GiB/s | 비율 | v3.6.1 작업 중 RSS MiB |',
        '|---:|---:|---:|---:|---:|']
    for r in z:
        if r['version']!='v3.6.1':continue
        a=next(x['metrics'] for x in z if x['version']=='v3.6.0' and x['size']==r['size']);b=r['metrics']
        lines.append('| {} | {} | {} | {:.3f} | {} |'.format(r['size']//1024,fmt(a['gib_sec']),fmt(b['gib_sec']),b['gib_sec']['median']/a['gib_sec']['median'],fmt(b['middle_rss_mib'])))
    lines+=['','![크기별 비교](allocation-size-v361/size-sweep.png)','',
        '[다섯 버전 크기 전체 표](allocation-size-v361/tables.md).','',
        '## 통계 진단과 소스 해석','',
        'A가 1000개를 할당하고 B가 모두 해제한 진단에서 전체 최종 current는 0이었다. '
        '자동 병합을 끄고 collect를 반복한 시점에서 64 B의 파생 해제량은 A에 64000 B, B에 0 B로 '
        '귀속되었다. 4 KiB는 A에 163840 B, B에 3932160 B로 나뉘었다. '
        '이 패턴은 v3.5.3/v3.6.0/v3.6.1에서 같았다. 파생 해제량은 실제 free 호출 횟수가 아니다.',
        'v3.6.1 기본 page_reclaim_on_free는 0, 통계 병합 임계값은 4 MiB다. '
        'v3.6.0의 1, 512 KiB와 다르며 pagemap/process 상태도 바뀌었다. '
        '이번 비교만으로 각 변경의 개별 인과 효과는 분리하지 않았다. '
        '[소스 근거](v361-source-notes.md)를 참고한다.','',
        '## 검증과 한계','',
        '모든 본 측정은 frozen hash, library/binary SHA, 버전/경로, 객체 수·checksum·최종 생존량, '
        'CPU 배치, swap/throttling을 검증했다. 실패한 측정을 삭제하거나 제외하지 않았다. '
        '준비 중 runner 생성의 문자열 검증이 한 차례 중단됐으며 측정 전에 수정했다. '
        '이는 allocator 실패나 제외 표본이 아니다.',
        '분석 출력에서 Windows cp949 인코딩 오류가 발생해 콘솔 출력을 ASCII 요약으로 수정하고 '
        '분석을 재실행했다. Windows Git의 실행 비트 표시 차이는 내용 검증과 구분했다. '
        '컨테이너 빌드 시에는 원본 checkout이 clean인지 검증했으며 upstream 내용을 수정하지 않았다.',
        '실제 동시 처리 본 측정 시간은 {:.3f}–{:.3f}초, 전체 관찰의 프로세스 peak RSS는 '
        '{:.2f} MiB였다. 동시 처리 본 측정의 major fault 합계는 {}이다. '
        'pilot 목표 3.5초보다 짧은 실행도 있으며 작업량을 사후 변경하지 않았다.'.format(
            *status['measured_concurrent_seconds_range'],status['process_peak_rss_mib'],status['measured_concurrent_major_faults']),
        '3회 반복, WSL2 가상화, 미통제 host 부하·주파수 때문에 작은 차이의 유의성이나 동등성을 주장하지 않는다. '
        'p99, perf cycles/instructions, 실제 응용 성능, CPython/fork/Rust/WASI 기능, '
        'MI_SECURE=MINIMAL, 정책별 인과 대조는 이번 범위에 포함하지 않았다. '
        'RSS 잔류만으로 누수라 판단하지 않으며 idle 이후 관측하지 않은 반환 시점을 추정하지 않는다.','',
        '## 재현과 자료','',
        '[계획](v361-plan.md) · [재현 명령](../observation/RELEASE_V361.md) · '
        '[검증 상태](../experiments/release-v361-v1/status.json).',
        '원자료는 results/release-v361-v1, results/purge-delay-v361-v1, '
        'results/allocation-size-v361-v1에 보존한다. 각 experiments 디렉터리에 plan, '
        'artifacts, summary와 raw-index를 보존하며 figures는 docs의 대응 디렉터리에 있다.','']
    spaced=[]
    for line in lines:
        if line and spaced and spaced[-1] and not line.startswith('|') and not spaced[-1].startswith('|'):
            spaced.append('')
        spaced.append(line)
    (ROOT/'docs/v361-report.md').write_text('\n'.join(spaced),encoding='utf-8')
    (ROOT/'experiments/release-v361-v1/ratios.json').write_text(json.dumps(ratios,indent=2)+'\n')
    print('Generated docs/v361-report.md')

if __name__=='__main__':main()
