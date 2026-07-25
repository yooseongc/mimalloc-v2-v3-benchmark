# r20 native-request 고정-worker 성능 예측 보고서

실행 상태: 완료  
실행일: 2026-07-25  
원시 데이터: `results/raw/`의 `r20-*` record 60건  
집계: `results/summaries/native-persistent-r20.json`

## 목적

수백 일 동안 thread가 유지되는 `io_context` 기반 네트워크 중계·DLP 프로그램을 단순화해, 고정 worker 사이의 task ownership transfer와 cross-thread free를 비교한다. r19의 `strace` 진단과 달리 이 실험은 `strace` 없이 처리량, CPU time, page fault, RSS 관측값을 수집했다.

두 버전은 **각자 문서화한 native large-OS-page request만** 사용했다.

| 버전 | 적용 환경 변수 |
|---|---|
| v2.1.2 | `MIMALLOC_LARGE_OS_PAGES=1` |
| v3.4.3 | `MIMALLOC_ALLOW_LARGE_OS_PAGES=1` |

두 변수는 이름·내부 의미가 동일하다고 가정하지 않는다. 따라서 r20은 동일 정책(normalized-policy) 비교가 아니라, 각 버전의 native large-page 요청 상태에서의 운영 예측 실험이다.

## 조건

- Rocky Linux 8 컨테이너, 네트워크 비활성화
- THP=`madvise`, Docker cpuset `0,2,4,6,8,10,12,14`, memory node 0
- 4 producer + 4 consumer, 총 8개 worker를 timed region 이전에 생성·pinning
- 각 producer는 1억 operation을 수행하고 pointer를 bounded MPMC queue로 전달하며, consumer가 free
- queue capacity 65,536, touch mode `first-and-last`
- `fixed-small`(64 B) 및 `mixed-wide`(16 B–64 KiB) workload별 15 paired repetition
- block 안의 v2/v3 실행 순서는 고정 seed로 무작위화하고, 각 repetition은 fresh process

## 결과

아래 절대값은 버전별 15회 중앙값이다. 비율은 같은 repetition을 짝지은 `v3 / v2` 중앙값이다.

| Workload | 지표 | v2.1.2 | v3.4.3 | 중앙 v3/v2 |
|---|---|---:|---:|---:|
| fixed-small | throughput | 5.34 Mops/s | 5.43 Mops/s | 1.019 |
| fixed-small | user CPU time | 148.693 s | 146.663 s | 0.986 |
| fixed-small | system CPU time | 0.412 s | 0.017 s | 0.045 |
| fixed-small | minor faults | 88,411 | 1,204 | 0.013 |
| fixed-small | 관측 종료 RSS | 9.42 MiB | 13.54 MiB | 1.432 |
| mixed-wide | throughput | 5.53 Mops/s | 5.74 Mops/s | 1.012 |
| mixed-wide | user CPU time | 142.731 s | 136.300 s | 0.986 |
| mixed-wide | system CPU time | 1.174 s | 2.658 s | 2.125 |
| mixed-wide | minor faults | 311,895 | 253,720 | 0.701 |
| mixed-wide | 관측 종료 RSS | 299.16 MiB | 480.89 MiB | 1.130 |

`fixed-small` 처리량 비율의 관측 범위는 0.879–1.200, `mixed-wide`는 0.887–1.303이었다. 따라서 1–2% 수준의 처리량 중앙값 차이를 보편적 성능 우위로 확정하지 않는다.

## 해석

### fixed-small task buffer

v3.4.3은 처리량·user CPU에서 소폭 유리했고, system CPU time과 minor fault는 이 workload에서 크게 낮았다. 그러나 관측 종료 RSS는 v3가 더 높았다. 작은 task buffer와 빈번한 cross-thread free가 지배하는 경우, v3 native request가 CPU/VM fault 관점에서 유망하다는 신호지만, RSS 비용도 함께 확인해야 한다.

### mixed-wide task buffer

v3.4.3은 중앙 처리량과 user CPU에서 약간 유리하고 minor fault도 낮았다. 반면 system CPU time은 중앙값 기준 약 2.13배, 관측 종료 RSS는 약 1.13배였다. 이 경우에는 r19에서 확인한 v3의 `madvise` 활동 증가가 kernel CPU와 메모리 유지 비용으로 나타날 가능성을 배제할 수 없다.

따라서 대상 프로그램의 buffer 크기 분포가 넓고 4 KiB 이상 객체가 자주 섞이면, v3.4.3의 작은 처리량 이득만으로 전환을 권고할 수 없다. system CPU, tail latency, 장기 RSS plateau를 실제 traffic에서 우선 확인해야 한다.

## RSS 필드의 한계

harness JSON 필드명은 `peak_rss_bytes`이지만, remote-free 경로는 worker join 뒤 `/proc/self/status`에서 한 번 관측한 RSS를 기록한다. 따라서 이 표의 RSS는 true peak RSS가 아니라 **관측 종료 RSS**로 해석한다. 특히 mixed-wide RSS 비율에는 반복 간 큰 변동도 있어 long-run memory stability 판단에 사용하지 않는다.

## r19와 함께 보는 결론

- r19: v3.4.3에서 THP `AnonHugePages`는 관측됐지만 `madvise` 총 호출이 v2보다 많았다.
- r20 fixed-small: v3는 낮은 system CPU·fault와 소폭 높은 처리량을 보였다.
- r20 mixed-wide: v3는 낮은 fault·소폭 높은 처리량과 함께 높은 system CPU·RSS 관측값을 보였다.

즉 native request 상태에서 v3.4.3이 시스템 부하에 항상 유리하다고 말할 수 없다. 작은 고정 크기 task가 주로 흐르면 v3의 추가 검증 가치가 높고, 넓은 크기 분포의 buffer/DLP 객체가 많으면 v2.1.2이 더 예측 가능한 kernel 부하와 메모리 발자국을 보일 가능성도 있다.

## 운영 권고

다음 canary는 실제 `io_context` worker 수와 buffer size histogram을 유지한 채, v2/v3 각각 native request 상태에서 최소 한 traffic 주기 이상 실행한다. 채택 기준은 처리량만이 아니라 다음의 동시 충족이다.

1. p99/p99.9 latency와 CPU/request가 v2 baseline보다 악화하지 않을 것
2. RSS의 시간당 증가 기울기와 cgroup peak가 memory budget 안에 있을 것
3. `madvise` 호출률, system CPU, minor/major fault가 workload phase별로 설명 가능할 것
4. crash, OOM, allocator validation, pointer accounting 오류가 없을 것

이 보고서는 primary normalized-policy 결과와 합산하지 않는다.
