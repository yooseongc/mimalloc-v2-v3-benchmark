# r19 syscall·large-page 진단 보고서

실행 상태: 완료  
실행일: 2026-07-25  
범위: mimalloc v2.1.2와 v3.4.3의 짧은 diagnostic-only 비교  
원시 데이터: `results/raw/r19/` (12 records)  
집계: `results/summaries/diagnostic-r19.json`

## 목적

이 진단은 v3.1.5에서 관찰했던 두 현상을 v3.4.3에서 좁은 조건으로 확인하기 위해 수행했다.

1. `mmap`, `munmap`, `madvise`, `brk` syscall이 v2보다 많이 발생하는지
2. large-page 관련 정책에서 실제 `AnonHugePages`가 관측되는지

이는 primary throughput 비교가 아니다. 장기 네트워크 중계·DLP 프로그램의 안정성이나 실제 traffic의 syscall 비율을 직접 증명하지 않는다.

## 조건

- Rocky Linux 8 컨테이너, 네트워크 비활성화
- Docker cpuset `0,2,4,6,8,10,12,14`, memory node 0
- host THP=`madvise` 유지; host-wide 설정 변경 없음
- `large_alloc`: 64 KiB–64 MiB 크기 순환, `per-page` touch, 각 allocation을 200 ms 유지한 뒤 free
- policy별·버전별 3회 fresh process 실행, v2/v3 순서는 paired block 안에서 무작위화
- `strace -f -c`로 syscall을 수집하고, benchmark child PID의 `smaps_rollup`/`status`를 50 ms 간격으로 sample

정책 arm은 아래와 같다.

| 정책 | v2.1.2 | v3.4.3 | 비교 성격 |
|---|---|---|---|
| upstream-default | 환경 변수 없음 | 환경 변수 없음 | 기본 정책 비교 |
| version-native large-OS-page request | `MIMALLOC_LARGE_OS_PAGES=1` | `MIMALLOC_ALLOW_LARGE_OS_PAGES=1` | 버전별 문서화 요청을 사용한 진단. 의미가 완전히 같은 normalized policy가 아님 |

## 결과

아래 값은 각 3회 실행의 중앙값이다. syscall 값은 process 시작부터 종료까지의 총 호출 수이며, allocation operation당 값이 아니다.

| 정책 | 버전 | elapsed | `mmap` | `munmap` | `madvise` | minor fault | 최대 `AnonHugePages` | 최대 RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| upstream-default | v2.1.2 | 14.433 s | 28 | 1 | 30 | 131,990 | 0 B | 84.0 MiB |
| upstream-default | v3.4.3 | 14.273 s | 29 | 1 | 748 | 11,751 | 86.0 MiB | 89.7 MiB |
| version-native request | v2.1.2 | 14.044 s | 32 | 1 | 2 | 42 | 84.0 MiB | 87.6 MiB |
| version-native request | v3.4.3 | 14.268 s | 32 | 1 | 748 | 11,751 | 86.0 MiB | 89.7 MiB |

`brk`의 중앙값은 네 그룹 모두 1회였다. 각 summary 값의 최소·최대는 `results/summaries/diagnostic-r19.json`에 보존한다.

## 관측과 해석

### v3.4.3의 `madvise` 호출

이 diagnostic workload에서는 v3.4.3이 양쪽 policy에서 중앙값 748회의 `madvise`를 보였다. v2.1.2 upstream default의 30회와 비교하면 약 25배, v2 native large-OS-page request의 2회와 비교하면 매우 큰 차이다. `mmap`/`munmap`은 양쪽 버전에서 수십 회·1회 수준으로 큰 차이가 없었다.

따라서 “v3 계열에서 syscall이 늘었다”는 기존 경험은 **v3.4.3의 이 large-allocation/per-page-touch 조건에서도 `madvise`에 한해서 재현됐다**고 말할 수 있다. 다만 이 수치는 `strace`가 benchmark process 전체(동적 loader·초기화·종료 포함)를 추적한 총계이며, 장기 서비스의 steady-state task 하나당 syscall 수는 아니다.

### large-page 관측

v3.4.3은 upstream default와 version-native request 모두에서 최대 `AnonHugePages` 약 86 MiB를 보였다. 따라서 이 호스트·컨테이너·THP=`madvise`·이 workload에서는 v3.4.3이 THP 사용을 막았다는 증거가 없다. 오히려 sampled process에서는 huge anonymous mapping이 관측됐다.

v2.1.2 upstream default의 `AnonHugePages`는 0 B였고, v2의 native request에서는 약 84 MiB가 관측됐다. v3 native request arm은 default와 같은 syscall·`AnonHugePages` 중앙값을 보였다. 이 결과만으로 옵션이 무효라고 단정할 수는 없지만, 적어도 이 조건에서 request가 default보다 추가 효과를 보였다는 관측은 없다.

`AnonHugePages`는 Linux THP 관측 지표다. 이것만으로 명시적 large OS page 또는 HugeTLB 1 GiB page의 사용을 증명하지 않으며, HugeTLB는 이번 진단의 범위 밖이다.

### 성능·메모리 안정성에 대한 의미

hold 시간이 elapsed 대부분을 차지하므로 네 elapsed 중앙값 차이를 allocator 처리량 우위로 해석하지 않는다. 최대 RSS도 한 개의 large object를 유지하는 짧은 관측값일 뿐, 수백 일 실행 프로그램의 RSS plateau나 memory leak 여부를 말해 주지 않는다.

이번 결과는 장기 canary의 진입 기준을 더 분명하게 만든다.

- v3.4.3을 검토할 때 `madvise` 호출률과 minor fault·tail latency를 함께 관측해야 한다.
- large page가 필요한 배포에서는 환경 변수의 존재만 확인하지 말고, 실제 process의 `AnonHugePages`와 workload별 page-fault를 확인해야 한다.
- v3 default와 v2 default의 purge policy 차이를 allocator 알고리즘 차이로 오인하지 않도록, production canary에서는 `MIMALLOC_PURGE_DELAY`를 맞춘 arm을 별도로 둬야 한다.

## 한계

- 3 paired repetition의 짧은 진단이며, 수백 일 운영·실 traffic·고정 `io_context` worker의 task 분포를 재현하지 않는다.
- `strace` 자체가 실행에 overhead를 추가한다. 모든 비교군에 동일하게 적용했지만, throughput 수치로 사용하지 않는다.
- `large_alloc`은 64 KiB–64 MiB 순환이며 실제 네트워크 buffer/DLP 검사 객체의 크기·수명 분포와 다를 수 있다.
- host THP는 `madvise` 한 조건만 사용했다. `never` 또는 다른 커널/host에서 같은 결과를 보장하지 않는다.

## 결론

v3.4.3은 이 조건에서 THP 사용이 관측됐으므로 “large page를 못 쓰게 막는다”는 과거 v3.1.5 현상을 그대로 재현하지 않았다. 반면 `madvise` 호출은 v2.1.2보다 현저히 많았다. 따라서 대상 프로그램의 v3.4.3 도입은 large-page 사용 여부만으로 막을 이유는 줄었지만, 장기 canary에서 syscall·fault·tail latency가 반드시 통과해야 하는 조건으로 남는다.

이 진단 결과는 [확정 primary 비교 보고서](experiment-report.md)의 600개 final-comparison record와 합산하지 않는다.
