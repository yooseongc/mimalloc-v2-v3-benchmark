# r22 NUMA balancing-off tcpio 파이프라인 실험 설계

Design status: Frozen
Design revision: tcpio-r22-amendment-v1; frozen pilot plan SHA-256 `cb28289d682270e6a30ab9156c5c2c2ab2601b04fd29dc35c606ad7a1c90ab50`
Frozen at: 2026-07-26T16:27:26+09:00

## 목적과 가설

r22는 기존 allocator microbenchmark와 분리하여
`tcpio → policy → 원래 tcpio → record → free` 소유권 이동을 재현한다.
단일 NUMA 호스트에서 NUMA balancing을 0으로 고정한 조건의 allocator 성능과
고정 tcpio worker 운용 적합성만 판정한다.

사전 가설은 다음과 같다.

1. v3.4.3은 upstream-default에서 v2.1.2 throughput의 97% 이상을 유지한다.
2. v3.4.3의 end-to-end p99와 CPU/op는 v2.1.2의 105% 이하이고 peak RSS는
   110% 이하이다.
3. allocator-only보다 service stage-work에서 allocator 차이가 작아진다.
4. normalized purge/THP 정책은 버전 기본 정책 차이로 인한 RSS·fault 차이를
   줄인다.

결과를 확인한 뒤 가설, gate 또는 제외 기준을 소급 변경하지 않는다.

## 비교 대상과 통제

- microsoft/mimalloc v2.1.2:
  `43ce4bd7fd34bcc730c1c7471c99995597415488`
- microsoft/mimalloc v3.4.3:
  `152fbf2634aeafca3774df791b0a77683035f076`
- 두 arm은 동일 Rocky Linux 8 image, benchmark binary, cpuset, seed,
  operation count, queue/bank 크기, warm-up을 사용한다.
- allocator는 동일 binary에 `LD_PRELOAD`하며 절대 경로, SHA-256,
  `mi_version`을 매 실행 검증한다.
- 실행 중 network를 끄고 fresh process를 사용한다.

독립 변수는 allocator version, topology, stage-work, runtime policy이다.
종속 변수는 throughput, elapsed, end-to-end latency, 역할별 CPU/op,
system CPU, page fault, 외부 sampled peak RSS/PSS/VmHWM/AnonHugePages,
cgroup peak와 queue/bank 지표이다. host load, frequency, thermal state는
수집하되 변경할 수 없으면 uncontrolled variable로 남긴다.

## workload와 thread topology

tcpio가 payload를 `malloc()`하고 policy 처리 뒤 `origin_tcpio`별 return
queue로 돌려받는다. 원래 tcpio가 record shard로 넘기며 record가 최종
`free()`한다. shard는 `origin_tcpio % record_count`다.

- isolated: 3 tcpio + 4 policy + 1 record를 CPU
  `0,2,4,6,8,10,12,14`에 worker 순서대로 pinning한다.
- service-like: 8 tcpio를 위 physical CPU에 pinning한다. 10 policy와
  2 record는 container의 `0-15` logical cpuset에서 scheduler가 배치한다.
- 모든 thread와 queue, bank, size/seed 상태는 timed region 전에 만든다.
- 같은 worker/queue로 warm-up을 drain한 뒤 전체 worker를 pause하고 측정
  counter를 분리한 상태에서 barrier를 해제한다.
- tcpio는 pending ingress보다 origin return drain을 항상 우선한다.

queue와 bank는 다음과 같다.

- tcpio→policy bounded MPMC: 65,536
- policy→origin tcpio queue: 8,192/tcpio
- tcpio→record shard queue: 8,192/record
- record worker당 double bank: 16 MiB 또는 4,096 pointer 도달 시 seal/swap
- warm-up과 종료 시 partial bank도 반드시 drain

`tcp-proxy-v1` payload는 64 B 10%, 256 B 15%, 1 KiB 25%, 4 KiB 30%,
16 KiB 15%, 64 KiB 5%의 deterministic synthetic distribution이다.
운영 traffic 재현으로 표현하지 않는다.

`allocator` stage-work는 각 stage에서 first-and-last만 touch한다.
`service`는 ingress full-write, policy cache-line scan과 고정 integer mix,
return tcpio full-buffer XOR, record cache-line checksum을 수행한다.
고정 seed는 `0x22c0ffee`다. 1/1,024 message에서만 ingress부터 final
record까지 latency를 측정하고 p50/p90/p95/p99/p99.9/max를 저장한다.

## 정책과 host-state epoch

모든 epoch에서 `/proc/sys/kernel/numa_balancing=0`과 online NUMA node가
하나뿐임을 실행 전후 검증한다.

- upstream-default: host THP=madvise, `MIMALLOC_*` 미설정
- normalized: host THP=never, 두 버전에 `PURGE_DELAY=1000`,
  `ARENA_PURGE_MULT=1`, `ARENA_EAGER_COMMIT=0`, `PURGE_DECOMMITS=1`,
  `USE_NUMA_NODES=1`; v2 `LARGE_OS_PAGES=0`; v3
  `ALLOW_LARGE_OS_PAGES=0`, `ALLOW_THP=0`

host controller는 기존 THP와 NUMA balancing을 서로 다른 state file에
저장한다. 중복 apply를 거부하고 write 후 read-back한다. 정상 종료, 오류,
INT, TERM에서 두 상태를 독립 복원한다. 일반 runner는 host 값을 변경하지
않고 불일치만 거부한다.

## 실행 단계와 무작위화

1. unit/correctness와 allocator별 smoke
2. 각 핵심 cell 3 paired pilot
3. pilot median이 10–30초가 되도록 topology/stage-work별 operation count 결정
4. calibration JSON으로 final plan freeze
5. policy별 host epoch에서 final 실행
6. 분석 및 보고서 생성

final matrix는 2 topology × 2 stage-work × 2 policy × 2 allocator ×
15 repetition = 240 measured runs이다. topology/policy별 queue-only
control은 2 allocator × 3 repetition, 총 24회이며 allocator 결과에서
빼지 않는다. 동일 cell/repetition의 v2/v3를 한 block으로 유지하고 frozen
seed로 block 및 block 내부 순서를 무작위화한다.

예상 measured 시간은 final 본 실행 약 80분(평균 20초 가정), control 약
8분이며 process setup과 host sampling을 포함하면 2시간 내외다. pilot은
보정 전 약 15–30분으로 예상한다. queue가 worst-case 64 KiB payload로
가득 찰 수 있으므로 smoke/pilot에서 cgroup headroom을 확인하고, OOM 또는
swap 발생 시 final을 시작하지 않는다.

## correctness, 측정과 invalid 기준

allocation→policy→origin tcpio→record의 count와 sequence checksum이 모두
일치해야 한다. record shard의 measured-run seen table로 duplicate를 찾고,
모든 pointer가 정확히 한 번 free되며 outstanding=0이어야 valid다.
queue wrap-around, bank threshold/partial flush, routing, producer completion,
CLI validation은 unit/smoke에서 확인한다.

runner는 100 ms마다 child의 RSS, PSS, VmHWM, AnonHugePages를 저장하고
cgroup peak를 보존한다. benchmark 종료 시 RSS는 peak로 대체하지 않는다.
역할별 thread CPU, process user/system CPU, minor/major fault, queue
occupancy/full/empty wait/backpressure, bank seal/saturation도 기록한다.

다음 실행은 raw record를 보존한 채 invalid 처리한다.

- allocator path/SHA/version, benchmark SHA, cpuset 또는 affinity 불일치
- NUMA balancing이 0이 아니거나 single-NUMA가 아니거나 policy THP 불일치
- 예상하지 않은 inherited `MIMALLOC_*`
- pointer count/checksum/duplicate/outstanding 오류 또는 비정상 종료
- aggregate queue backpressure가 elapsed의 5% 초과
- 정상 drain 조건에서 record bank 동시 threshold saturation이 반복
- CPU throttling, swap/OOM, host state의 실행 중 변경

unsupported metric은 null/unavailable이며 0으로 대체하지 않는다.

## 통계와 적합성 판정

각 final cell에 valid/invalid 수, median/mean/stddev/CV/min/max/p25/p75/IQR와
95% CI를 보고한다. v3/v2는 동일 block의 paired ratio와 10,000회 paired
bootstrap median 95% CI를 사용한다. throughput(v3/v2) ≥0.97,
p99 ≤1.05, CPU/op ≤1.05, peak RSS ≤1.10이며 correctness/provenance/
affinity 오류가 0이어야 gate를 통과한다.

upstream-default의 모든 cell이 통과하면 “기본 업그레이드 적합”,
normalized만 통과하면 “명시적 정책 조정 조건부 적합”, 둘 다 실패하면
“v2 유지”로 판정한다.

## 재현, 한계와 validity threat

frozen smoke/pilot plan은 `manifests/execution-plan-tcpio-r22-*.json`에 둔다.
final plan은 pilot calibration 없이는 생성기가 거부한다. raw 결과는
`results/raw/r22/`, 시계열과 log는 `results/logs/r22/`, summary는
`results/summaries/tcpio-r22.json`이다.

단일 NUMA라 page migration이나 balancing on/off 효과를 판정할 수 없다.
synthetic payload와 고정 integer work는 실제 tcp stack, policy engine,
logging server 지연을 재현하지 않는다. scheduler noise, SMT interference,
frequency/thermal 변화, queue implementation 비용과 sampling 간격 사이의
짧은 RSS peak 누락이 남는 threat다. paired randomization, fixed input,
queue-only control, provenance 검증으로 이를 줄이되 제거했다고 주장하지 않는다.

## Amendments

Frozen 이후 변경은 기존 내용을 덮어쓰지 않고 이유, 시각, 영향받는 plan
revision과 함께 이 절에 추가한다.

### Amendment v2 — kernel-unsupported NUMA control 및 ASAN 제외

Amendment status: Frozen
Amendment revision: tcpio-r22-amendment-v2; frozen pilot plan SHA-256 `d47448745e5f0234d99d4c06fd448296c573f8785d3eaf4bf4d04372fa1e22e5`
Frozen at: 2026-07-26T16:37:13+09:00

2026-07-26 사용자 결정으로 `/proc/sys/kernel/numa_balancing`과 ASAN을 필수
실행 전제에서 제외한다. 현재 실행 kernel은
`6.6.87.2-microsoft-standard-WSL2`, online NUMA node는 `0` 하나이며 kernel
config에는 `# CONFIG_NUMA_BALANCING is not set`이 확인됐다. 따라서 이
환경에서는 automatic NUMA balancing이 작동할 수 없지만, 이를
`numa_balancing=0`을 명시적으로 설정·검증한 결과로 표현하지 않는다.
raw record에는 control 값 `null`, requirement
`disabled-or-kernel-unsupported`를 기록한다.

새 plan은 `execution-plan-tcpio-r22a-smoke.json`과
`execution-plan-tcpio-r22a-pilot.json`이다. 기존 v1 frozen plan은 보존하고
v2 결과와 합산하지 않는다. 이 결과로 balancing on/off 차이 또는 다른
kernel에서의 동작을 결론 내리지 않는다.

ASAN은 pinned image에 필요한 `libasan.so.5.0.0`이 없어 제외한다. ASAN
성공을 주장하지 않으며 allocator provenance, exact-once seen table, count와
checksum, queue/bank/routing smoke를 r22a correctness gate로 사용한다.
ASAN 부재 자체는 performance run invalid 사유가 아니다.

### Amendment v3 — isolated record stage 재균형

Amendment status: Frozen
Amendment revision: tcpio-r22-amendment-v3; frozen pilot plan SHA-256 `25d3619a02cf97ce06e9df2b23ca454f824e3da726125fe61faea4c824ae5395`
Frozen at: 2026-07-26T16:46:33+09:00

amendment v2 pilot 72회 중 21회가 correctness가 아닌 queue backpressure
기준으로 invalid였다. isolated allocator에서는 record/return queue가
capacity에 도달했고, isolated queue-only에서는 ingress도 포화됐다. 이
관찰 뒤 기존 invalid 기준을 완화하지 않는다.

사용자 승인으로 isolated topology를 3 tcpio + 3 policy + 2 record로
재균형한다. 총 worker 8개와 physical-core pinning, payload, queue/bank 크기,
stage-work, 정책, 반복 수, 5% backpressure invalid 기준은 유지한다.
service-like topology는 8 tcpio + 10 policy + 2 record로 유지하지만 동일
revision의 새 block ID로 다시 실행한다.

새 plan은 `execution-plan-tcpio-r22b-smoke.json`과
`execution-plan-tcpio-r22b-pilot.json`이다. block ID는 `r22b-` prefix를
사용하며 v1/v2 결과와 합산하지 않는다. v3 pilot이 기준을 충족해야만
calibration과 final plan을 생성한다.

### Amendment v4 — backpressure를 측정 지표로 전환

Amendment status: Frozen
Amendment revision: tcpio-r22-amendment-v4; frozen pilot plan SHA-256 `4d843fd4044f7dbaf39e90711c5310402e47660cc829adde15f9f6d91f38cb94`
Frozen at: 2026-07-26T16:54:12+09:00

Final matrix frozen at: 2026-07-26T16:57:18+09:00
Final plan SHA-256: `1d4010ec02d919107a6757d4061c30c3dddc4fc3f854c52aab0f68ed39f978e6`

v3 record 재균형 뒤에도 isolated allocator와 queue-only에서 정상 flow
control의 aggregate backpressure가 elapsed 5%를 넘었다. 사용자 승인으로
v4부터 backpressure를 invalid 사유가 아닌 측정 지표로 전환한다. 이전
record를 소급 재분류하지 않고 `r22c-` prefix의 새 block 전체를 실행한다.

backpressure time, elapsed 대비 비율, queue별 full wait와 maximum occupancy는
raw record와 v3/v2 paired 분석에 계속 포함한다. correctness/count/checksum,
duplicate/outstanding, allocator·benchmark SHA/provenance, affinity/cpuset,
host-state, cgroup throttling/OOM/swap, 반복적인 record-bank 동시 threshold
saturation 기준은 그대로 invalid 사유다. topology는 v3의
3 tcpio + 3 policy + 2 record isolated 구성을 유지한다.

### Amendment v5 — competing-container 오염 제외와 clean-host 재실행

Amendment status: Frozen
Amendment revision: tcpio-r22-amendment-v5; frozen pilot plan SHA-256 `eec6313a816f045ab5b2cb26a1381b16ab6928e3da9e2aa6e3c51d365c9028ab`
Frozen at: 2026-07-26T17:17:27+09:00

Final matrix frozen at: 2026-07-26T17:20:41+09:00
Final plan SHA-256: `9ff64802ba7ed44a6a8be1e08f3cf98604fd0b85f1e2617d665ef3ca9ebfd716`

v4 final 실행 중 `docker ps --no-trunc` 감사에서 이전 deadlock smoke
컨테이너 두 개가 약 한 시간 동안 동일 CPU 집합을 점유한 사실을 발견했다.
따라서 amendment v2, v3, v4의 smoke, pilot 및 부분 final record를 성능
근거에서 전부 제외한다. raw는 수정·삭제하지 않고
`manifests/exclusions-tcpio-r22.json`에 사유와 container ID를 기록한다.

새 `r22d-` block은 competing mimalloc container가 없는 상태를 read-only
확인한 뒤 처음부터 smoke와 pilot을 다시 실행한다. calibration과 analysis는
`--design-revision tcpio-r22-amendment-v5`를 필수로 받아 다른 revision을
합산하지 않는다. topology와 backpressure metric-only 정책 등 v4의 나머지
조건은 유지한다.

강제 중단 시 foreground Python 때문에 bash trap이 지연되어 THP가 `never`에
남는 문제도 발견했다. controller는 runner를 background child로 관리하고
TERM/INT에서 child 종료 후 host state를 복원하도록 변경했다. 오염된 final
container 중단 직후 THP가 `never`임을 read-back했고, 기록된 원래 값
`madvise`로 수동 복원한 뒤 재실행한다.

### Amendment v6 — service-like 측정시간 재보정

Amendment status: Frozen
Amendment revision: tcpio-r22-amendment-v6
Frozen at: 2026-07-26T18:21:53+09:00
Final plan SHA-256: `3197dbcf4182c577d5dd95894182366f8bcdf242bdd19ac56f08753f5ced2dea`

v5 final audit에서 isolated의 모든 measured run은 5초 이상이었지만,
service-like의 일부 run은 frozen 설계의 최소 5초에 미달했다. 결과를 본 뒤
제외 기준을 바꾸지 않고, v5 final의 allocator-version 합동 median 처리율에
20초를 곱한 보수적 operation count로 service-like 전체 cell과 queue-only
control만 새 `r22e-` block에서 재실행한다. operation count는 allocator
버전에 관계없이 각 stage-work에서 동일하다.

isolated v5 결과는 변경 없이 유지하며 service-like v6 결과와 repetition을
합산하지 않는다. 최종 분석은 topology별로 서로 겹치지 않는 frozen
revision을 선택한다: isolated=`tcpio-r22-amendment-v5`,
service-like=`tcpio-r22-amendment-v6`. v6 operation count는 allocator
63,420,667, service 34,022,222이고, 근거는
`config/tcpio-r22e-calibration.json`에 보존한다.
