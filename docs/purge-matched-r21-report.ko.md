# r21 purge-delay 일치 RSS·AnonHugePages 검증 보고서

실행 상태: 완료  
실행일: 2026-07-25  
원시 데이터: `results/raw/r21/` (유효 30 records)  
집계: `results/summaries/purge-matched-r21.json`

## 질문

r20 native-request fixed-worker mixed-wide workload에서 v3.4.3의 관측 종료 RSS가 v2.1.2보다 높았던 이유가, 두 버전의 기본 purge delay 차이인지 검증한다.

## 조건

- r20과 같은 4 producer + 4 consumer fixed-worker `remote_free`, `mixed-wide`(16 B–64 KiB), operation 1억
- Docker cpuset `0,2,4,6,8,10,12,14`, memory node 0, host THP=`madvise`, 네트워크 비활성화
- native large-OS-page request 유지
  - v2.1.2: `MIMALLOC_LARGE_OS_PAGES=1`
  - v3.4.3: `MIMALLOC_ALLOW_LARGE_OS_PAGES=1`
- 두 버전에 공통으로 `MIMALLOC_PURGE_DELAY=1000` 적용
- 15 paired fresh-process repetition, block 안의 v2/v3 순서는 seed 기반 무작위화
- `strace` 없이 benchmark child PID의 `smaps_rollup`을 100 ms마다 sampling

native large-page request 변수는 여전히 version-native이며 완전한 동일 정책으로 가정하지 않는다. 이번 검증에서 맞춘 변수는 purge delay 하나다.

## 결과

아래 절대값은 버전별 15회 중앙값이며, 비율은 paired `v3/v2` 중앙값이다.

| 지표 | v2.1.2 | v3.4.3 | 중앙 v3/v2 |
|---|---:|---:|---:|
| throughput | 5.743 Mops/s | 6.044 Mops/s | 1.015 |
| user CPU time | 135.796 s | 129.305 s | 0.990 |
| system CPU time | 0.799 s | 2.024 s | 2.548 |
| minor faults | 230,683 | 220,463 | 0.964 |
| 최대 sampled RSS | 908.84 MiB | 543.65 MiB | 0.597 |
| 마지막 유효 sampled RSS | 908.84 MiB | 512.92 MiB | 0.570 |
| 최대 `AnonHugePages` | 4 MiB | 388 MiB | 97.0 |

최대 sampled RSS의 paired 비율은 15회 모두 0.566–0.635 범위였다. r20의 종료 시점 단발 RSS 관측과 달리, r21은 실행 중 시계열을 수집했으며 이 방향은 반복 간 일관됐다.

## 판정

### r20의 높은 v3 RSS는 기본 purge delay 차이가 주원인이다

r20은 native request만 적용해 v2의 기본 purge delay(10 ms)와 v3의 기본 purge delay(1000 ms)를 그대로 비교했다. 그 조건에서는 mixed-wide 관측 종료 RSS의 v3/v2 중앙 비율이 1.130이었다.

r21에서 두 버전 모두 1000 ms로 맞추자 같은 workload의 최대 sampled RSS 비율은 0.597로 역전됐다. 따라서 “v3 자체가 항상 더 많은 RSS를 쓴다”는 가설은 이 조건에서 지지되지 않는다. 기본 purge 정책이 r20 RSS 관측의 큰 교란 요인이었다는 결론이 가장 타당하다.

### v3의 THP 사용과 system CPU trade-off는 남는다

v3는 최대 `AnonHugePages` 약 388 MiB를 일관되게 보였고, v2는 4 MiB였다. v3의 낮은 sampled RSS 및 약간 높은 처리량은 이 backing policy와 관련될 수 있지만, allocator 내부 원인으로 확정하지는 않는다.

동시에 v3 system CPU time은 중앙값 기준 약 2.55배였다. r19의 높은 `madvise` 관측과 방향은 일치하지만, r21은 strace를 사용하지 않았으므로 system CPU 증가의 syscall별 원인을 직접 증명하지 않는다.

## 운영상 의미

대상 프로그램에서 v3.4.3을 평가할 때 RSS가 높게 보이면 먼저 `MIMALLOC_PURGE_DELAY`가 v2와 같은지 확인해야 한다. 기본값 그대로의 v2/v3 RSS 비교는 allocator 구조와 purge 정책을 동시에 비교하는 결과다.

그러나 purge delay를 맞춰도 v3의 system CPU 증가는 남았다. 따라서 canary의 채택 기준은 다음처럼 분리해야 한다.

1. memory budget/RSS 안정성: purge-matched arm에서 RSS time series와 cgroup peak를 비교
2. kernel 비용: 같은 arm에서 system CPU, `madvise` 호출률, page fault, p99/p99.9 latency를 비교
3. 성능: throughput·user CPU를 별도로 비교하고, 1–2% 수준의 중앙값 차이를 단독 채택 근거로 사용하지 않음

## 한계

- r21은 약 수십 초 길이의 fixed-worker workload이며, 수백 일 운영의 RSS 기울기나 실제 `io_context` task 분포를 대체하지 않는다.
- native large-page request 변수는 버전별 의미가 완전히 같다고 검증하지 않았다.
- `AnonHugePages`는 THP의 관측값이며 explicit HugeTLB 사용 증거는 아니다.

이 결과는 r20 및 primary normalized-policy 결과와 합산하지 않는 별도 진단이다.
