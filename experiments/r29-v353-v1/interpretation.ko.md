## 측정 후 해석 정정 (2026-09-21)

소스와 실제 Release 바이너리 재점검에서 서비스 record 계산이 최적화로
제거된 결함을 확인했다. 또한 아래의 allocator-only pipeline p99는
malloc 이후부터 free 직전까지의 큐 체류·중간 처리 시간이며 malloc/free
호출 지연시간이 아니다. 따라서 p99 10% 감소를 allocator 호출 성능 개선으로
해석하지 않으며, service 결과를 의도한 전체 서비스 작업의 성능으로 사용하지 않는다.
630건 valid는 당시 실행 검증 통과를 뜻하며 측정 방법의 타당성 보증은 아니다.
이 정정은 아래의 기존 해석보다 우선한다. 원시 결과와 동결 설계는 보존했다.
발견 사항과 후속 실험 요건은 [하네스 감사](r29-method-audit.md)에 기록했다.

## 주요 발견과 판단

v3.5.3의 일괄적인 성능 향상은 확인되지 않았다. v3.5.0 대비
8-worker mixed-wide local 처리량은 paired 비율 기준 약 6.1% 낮았다
(비율 0.9395, 95% CI 0.9197–0.9668). 이 셀의 allocation당 CPU 시간은
약 3.4% 증가했다. 반면 local 64 B/8-worker와 mixed-wide/1-worker의
처리량 차이는 신뢰구간이 1을 포함했다.

Remote fixed의 처리량 비율은 0.9957, remote mixed-wide는 1.0366이었다.
두 신뢰구간 모두 1을 포함하므로 remote-free 개선을 확정할 수 없다.
Queue-only 대조 실행도 library arm에 따라 5.20–6.43 M transfers/s였고,
v2.1.2/v3.5.0의 CV가 14.0–15.4%였다. 이 하네스의 queue·공유 카운터 비용과
환경 변동을 고려해야 하며, queue 시간을 allocator 시간에서 빼지 않았다.

별도 allocator-only pipeline의 p99는 paired 비율 기준 약 10.0% 짧아졌다
(0.8996, 95% CI 0.8408–0.9552). 서비스 작업을 포함한 pipeline과 p99.9는
신뢰구간이 1을 포함했다. 따라서 이 p99 개선을 실제 서비스 전반의
지연시간 개선으로 일반화하지 않는다.

기본 정책에서 모든 버전은 512 MiB를 해제한 뒤 5초 idle 동안 관측 가능한
RSS 반환이 없었다. v3.5.3의 normal/forced collect는 98.41%를 반환했고,
v3.5.0은 99.61%였다. v3.5.3의 collect 후 RSS 중앙값은 약 13.6 MiB였다.
Purge delay 0에서는 v3.5.3도 99.51%를 반환했지만, free 중앙값은
33.53 ms(기본값 0.29 ms), 다음 burst는 315.16 ms(기본값 40.11 ms)였다.
이 비용 비교는 각 조건의 중앙값을 비교한 것이며, 버전 간 paired 비율과
구분한다. 빠른 메모리 반환에는 해제·재할당 비용이 따른다.

배포 판단에서는 mixed-wide local 병렬 할당 비중이 높은 경우 이번 회귀를
실제 workload로 재확인할 필요가 있다. Remote-free 처리량 향상이나
기본 idle RSS 반환 개선만을 기대하는 업그레이드 근거는 확보하지 못했다.
Allocator-only pipeline의 p99 개선은 관찰됐으나 서비스 workload에서는
재검증해야 한다. 릴리스의 correctness 수정 가치는 성능 결과와 별도로
판단해야 하며, 이 실험은 모든 플랫폼에서 upstream 버그를 재현한 검사가 아니다.

표의 절대값은 버전별 중앙값이고, 비교 비율은 같은 repetition의 비율들을
구한 뒤 취한 중앙값이다. 따라서 절대 중앙값을 나눈 값과 다를 수 있으며,
변동이 큰 service p99에서는 방향도 달라진다. 모든 성능 판단은 표에
명시한 paired 추정값과 그 신뢰구간을 따른다.

이번 결과는 WSL2의 고정 vCPU 집합에서 얻은 결과다. 완전히 정규화한
THP/통계 기능 비교, bare-metal 재현, THP 모드 sweep, cross-NUMA,
secure/TLS build sweep, Windows-native 성능은 이번 revision에서 실행하지 않았다.
