# r23 tcpio THP=madvise + large-page-on 직접 비교 설계

Design status: Frozen
Design revision: tcpio-large-page-v1
Frozen at: 2026-07-26T19:48:22+09:00
Smoke plan SHA-256: `96fa133a345acb22c2aed5ace88171e19c0991d9a47364c4fc817b3d0420f2ac`

## 질문

실제 service-like `tcpio → policy → origin tcpio → record → free` 시나리오에서
THP=`madvise`와 large OS page 요청을 켰을 때 mimalloc v3.4.3이 v2.1.2보다
처리량과 drain 이후 VmRSS 반응성에서 좋아지는가?

이 시험은 r22의 정책 matrix와 합산하지 않는다. NUMA balancing control과
ASAN은 사용자 결정에 따라 실행 전제에서 제외하며, kernel에 NUMA balancing이
컴파일되어 있지 않다는 사실을 기록한다.

## 고정 조건

- service-like/service 한 cell만 사용한다.
- 8 tcpio는 physical-core CPU에 pinning하고 10 policy + 2 record는
  `0-15` cpuset에서 scheduler가 배치한다.
- payload, queue/bank, seed와 operation count는 v2/v3에서 동일하다.
- host THP는 `madvise`로 고정하고 종료·오류·중단 시 원래 값으로 복원한다.
- v2: `MIMALLOC_ALLOW_LARGE_OS_PAGES=1`
- v3: `MIMALLOC_ALLOW_LARGE_OS_PAGES=1`,
  `MIMALLOC_ALLOW_THP=1`
- 그 밖의 `MIMALLOC_*`는 설정하지 않아 실제 버전 기본 동작을 비교한다.
- 모든 allocation은 policy와 origin tcpio를 거쳐 record에서 정확히 한 번
  free되어야 한다.

## 두 가지 primary metric

1. throughput: timed region의 operation/s. 모든 pointer가 free될 때까지의
   elapsed만 포함한다.
2. VmRSS 반응성: timed region 종료, worker join, outstanding=0 직후를
   0 ms로 두고 동일 프로세스를 5초 유지하며 100 ms 간격으로
   `/proc/self/status`의 VmRSS를 기록한다. 0 ms, 1초, 5초 VmRSS,
   `VmRSS(5초)/VmRSS(0초)` retained ratio와 관측 감소가 1 MiB 이상일 때의
   half-release time을 비교한다.

외부 100 ms sampler의 peak VmRSS와 AnonHugePages는 large-page 요청이 실제
backing으로 이어졌는지 확인하는 보조 진단이다. 환경변수가 1이라는 사실만으로
실제 large page 사용을 주장하지 않는다.

## 실행과 판정

correctness smoke 한 pair를 먼저 실행한다. final은 동일 operation
34,022,222건으로 15 paired fresh-process repetitions을 seed 기반으로
무작위화한다.

v3가 명료하게 좋아졌다고 판정하려면 paired throughput median이 1보다 크고
bootstrap 95% CI도 1을 넘어야 하며, 1초 및 5초 VmRSS paired median이
v2 이하이고 release half-time이 느려지지 않아야 한다. throughput과 VmRSS가
서로 반대 방향이면 trade-off로 보고 “명료한 개선 아님”으로 판정한다.

## Amendment v2 — bounded-queue backpressure 분류 명시

Amendment status: Frozen
Amendment revision: tcpio-large-page-v2
Frozen at: 2026-07-26T19:49:50+09:00
Smoke plan SHA-256: `905d79b9c2878599035093c969104caaf926ff304dc7bdcb994c3f8d72fdb352`

Final matrix frozen at: 2026-07-26T19:50:46+09:00
Final plan SHA-256: `395104f0f2d7ebb9adbc3c830642579686b5d2d60b828224707487b001c20190`

v1 smoke 한 pair는 exact-once count, checksum, outstanding=0과 51개 VmRSS
sample이 모두 정상이었지만 plan에 backpressure 정책 필드가 없어 runner의
과거 기본값인 `invalid-over-5pct`가 적용됐다. bounded pipeline의 정상 flow
control은 primary metric이 아니므로 새 `r23b-` block에서
`backpressure_policy=metric-only`를 명시한다. v1 raw record는 수정하거나
재분류하지 않는다.

## Amendment v3 — VmRSS 관측 전 harness buffer 해제

Amendment status: Frozen
Amendment revision: tcpio-large-page-v3
Frozen at: 2026-07-26T20:11:38+09:00
Smoke plan SHA-256: `4a71eb7aa407b965e82a58cfc7964816f8340f39746bcf860354a122b06f57ff`

Final matrix frozen at: 2026-07-26T20:13:16+09:00
Final plan SHA-256: `091308bc8651b3c9fd3596c5d610adfd86dd2f3ebed306231cca96f96b35e85f`

v2 final 30회는 throughput과 pointer correctness는 유효했지만 post-drain
관측 동안 precomputed size sequence와 exact-once seen table 등
harness-owned dynamic buffer가 남아 있었다. 이 VmRSS는 allocator가 payload
free에 반응한 결과로 해석할 수 없으므로 v2 final의 VmRSS와 최종 판정을
사용하지 않는다.

v3는 queue storage, size sequence, warm-up sequence와 seen table을 worker
join 및 correctness 집계 직후 명시적으로 해제하고 그 다음 시점을
post-drain 0 ms로 정의한다. timed region 코드는 바꾸지 않았지만 benchmark
SHA가 달라졌으므로 처리량도 새 `r23c-` block 전체를 다시 실행하며 revision
사이의 repetition을 합산하지 않는다.
