# r23 THP=madvise + large-page-on tcpio 직접 비교 결과

Execution status: Executed
Design revision: `tcpio-large-page-v3`
Final records: 30/30 valid, 15 complete pairs
Decision: **v3는 VmRSS가 명확히 개선됐고 처리량은 소폭 높았지만 속도 우위는 확정되지 않음**

## 질문과 조건

실제 service-like/service `tcpio → policy → origin tcpio → record → free`
경로에서 다음 두 지표만 비교했다.

1. timed region throughput
2. 모든 pointer와 harness-owned buffer를 해제한 뒤 0~5초 VmRSS 반응

host THP는 `madvise`다. v2.1.2와 v3.4.3 모두
`MIMALLOC_ALLOW_LARGE_OS_PAGES=1`을 사용했고, v3에는
`MIMALLOC_ALLOW_THP=1`도 명시했다. 그 밖의 mimalloc 옵션은 설정하지 않아
버전별 실제 기본 동작을 비교했다.

각 allocator는 동일 34,022,222 operations, seed, payload, queue와 cpuset으로
15 paired fresh-process repetitions을 수행했다. 모든 run에서 allocation,
policy, origin return, record, free count/checksum이 일치했고 outstanding,
duplicate, lost pointer는 0이었다.

## 결과

| 지표 | v2 median | v3 median | paired v3/v2 median | bootstrap 95% CI |
|---|---:|---:|---:|---:|
| throughput | 1.245 Mops/s | 1.296 Mops/s | **1.017** | 0.979–1.063 |
| peak VmRSS | 953.3 MiB | 680.4 MiB | **0.730** | 0.620–0.886 |
| post-drain VmRSS 0 ms | 871.6 MiB | 268.0 MiB | **0.308** | 0.266–0.364 |
| post-drain VmRSS 1 s | 871.6 MiB | 268.0 MiB | **0.308** | 0.266–0.364 |
| post-drain VmRSS 5 s | 871.6 MiB | 268.0 MiB | **0.308** | 0.276–0.340 |

v3 throughput의 paired median은 v2보다 1.7% 높았다. 15 pair 중 11 pair에서
v3가 빨랐지만 bootstrap CI가 1을 포함하므로 “v3가 확실히 더 빠르다”고
결론 내리지는 않는다. 반대로 이 측정에서 의미 있는 처리량 저하도
중앙값으로 관측되지 않았다.

VmRSS 차이는 크고 반복 간 방향도 일관됐다. peak VmRSS는 v3가 약 27%
낮았고, drain 직후 retained VmRSS는 약 69% 낮았다. peak에서 첫 post-drain
sample까지 감소한 비율의 버전별 median은 v2 6.1%, v3 61.6%였다.

0 ms 이후 5초 동안에는 두 버전 모두 추가 VmRSS 감소가 없었다. 즉 v3는
대부분의 반환을 첫 post-drain 관측 전에 완료한 반면 v2는 높은 plateau를
5초 동안 유지했다. 따라서 half-release time은 양쪽 모두 계산할 수 없고,
반응성 차이는 immediate release와 retained plateau로 판단한다.

large-page 요청은 실제 backing으로 이어졌다. peak AnonHugePages median은
v2 약 496 MiB, v3 약 438 MiB였다. 이는 HugeTLB 1 GiB page가 아니라 Linux
THP/large anonymous backing 관측값이다.

## 결론

이 시나리오와 설정에서는 v3.4.3을 사용하는 것이 **적합하다**.

- 처리량: v2와 통계적으로 명확히 구분되는 속도 향상은 아니지만 median
  1.7% 향상이며 뚜렷한 회귀는 관측되지 않았다.
- VmRSS 반응성: v3가 명확히 우수하다. peak가 낮고 drain 직후 retained
  VmRSS가 v2의 약 31%다.

따라서 결론은 “v3가 확실히 더 빠르다”가 아니라
**“처리량을 유지하면서 VmRSS peak와 drain 후 retention을 크게 줄인다”**다.
이 결론은 현재 synthetic tcpio payload와 20-worker service-like topology,
THP=`madvise`, large-page request=on 조건에 한정한다.

## 생성물

- raw: `results/raw/r23/`
- memory series/log: `results/logs/r23/`
- summary: `results/summaries/tcpio-large-page-r23.json`
- frozen plan: `manifests/execution-plan-tcpio-r23c-final.json`
- design/amendments: `docs/tcpio-large-page-r23-design.ko.md`
