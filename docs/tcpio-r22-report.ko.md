# r22 tcpio 파이프라인 v2/v3 적합성 보고서

Execution status: Executed
Final decision: **명시적 정책 조정 조건부 적합**
Final records: 240/240 valid measured runs, 24/24 valid queue-only controls

## Executive summary

단일 NUMA 호스트의 `tcpio → policy → 원래 tcpio → record → free`
파이프라인에서 mimalloc v3.4.3은 normalized 정책의 4개 cell을 모두
통과했지만 upstream-default의 service-like 2개 cell을 통과하지 못했다.
따라서 기본값 그대로의 업그레이드는 권장하지 않고, 이 workload에서는
명시적인 purge/large-page/THP 정책을 적용하는 조건으로 적합하다고 판정한다.

upstream-default service-like allocator에서 v3/v2 median은 throughput
0.908, p99 latency 1.514, CPU/op 1.095, peak RSS 1.024였다. service
work에서도 각각 0.945, 1.672, 1.053, 1.038로 gate를 실패했다.
normalized service-like에서는 두 cell이 모두 통과했다. 이 결론은 r22
synthetic diagnostic에만 적용하며 r19–r21과 합산하지 않는다.

## 목적과 범위

메시지는 tcpio가 할당하고 policy 처리 후 origin tcpio로 돌아오며, tcpio가
record shard에 전달하고 record가 최종 `free()`한다. allocator-only work와
service-like memory work, isolated와 scheduler-assisted topology, upstream
default와 normalized policy를 비교했다.

`tcp-proxy-v1`은 64 B 10%, 256 B 15%, 1 KiB 25%, 4 KiB 30%,
16 KiB 15%, 64 KiB 5%인 고정-seed synthetic proxy다. 운영 트래픽을
재현한다고 주장하지 않는다. 정상 drain만 모델링하며 로그 서버 지연,
장기 backlog, OOM 회복, multi-socket/cross-NUMA는 범위 밖이다.

## 실제 환경

- CPU: AMD Ryzen 7 5700X, 8 physical core/16 logical CPU, 1 socket
- NUMA: node 0 하나, CPU 0–15, 약 32 GiB
- kernel: `6.6.87.2-microsoft-standard-WSL2`
- container: Rocky Linux 8,
  `rockylinux@sha256:9794037624aaa6212aeada1d28861ef5e0a935adaf93e4ef79837119f2a2d04c`
- toolchain: GCC/G++ 8.5.0, glibc 2.28, CMake 3.26.5,
  binutils 2.30, Python 3.6.8
- cgroup: v2, fixed cpuset/cpuset.mems, CPU quota 없음; run별
  `cpu.stat`, memory current/peak/events, swap을 수집
- network: 측정 컨테이너에서 disabled
- THP: upstream-default=`madvise`, normalized=`never`; 각 epoch 종료 후
  원래 `madvise`로 복원 확인
- HugeTLB: 예약 없음; normalized에서 allocator large OS page 요청을 비활성화

이 kernel은 `CONFIG_NUMA_BALANCING`이 컴파일되어 있지 않아
`/proc/sys/kernel/numa_balancing`이 없다. 따라서 사용자 결정에 따라 NUMA
balancing 제어를 실행 전제에서 제외했다. 결과를 “명시적으로 balancing=0을
설정한 비교”나 on/off 효과로 표현하지 않는다.

## 비교 대상과 provenance

- v2.1.2 commit `43ce4bd7fd34bcc730c1c7471c99995597415488`,
  library SHA-256
  `03a21de3a984a745c1bfe8ae6a6ad2ee79e4202c3364745ccba541e539c51f06`
- v3.4.3 commit `152fbf2634aeafca3774df791b0a77683035f076`,
  library SHA-256
  `192b3a11694cbb86bbd54b5e2e63ed51942f16ad4a11e55fb0bd8fa2ad38bfb2`
- 동일 Release benchmark SHA-256
  `11d99bbf8c030b67774b9b138473a56ace7709863f704014043978f7fb36af44`

모든 run에서 절대 library path, SHA, `mi_version`, `/proc/<pid>/maps`,
benchmark SHA와 affinity를 검증했다. correctness, allocator provenance,
affinity 오류는 0건이었다.

## workload와 실행 설계

- isolated: 3 tcpio + 3 policy + 2 record를 CPU
  `0,2,4,6,8,10,12,14`에 pinning
- service-like: 8 tcpio를 위 physical-core CPU에 pinning하고 10 policy +
  2 record는 `0-15` cpuset에서 scheduler 배치
- ingress MPMC 65,536, origin return queue 8,192/thread, record queue 8,192
- record worker별 16 MiB/4,096 pointer double bank, partial bank drain
- latency 1/1,024 sampling, process memory 100 ms 외부 sampling
- allocator마다 15 paired repetitions/cell, queue-only는 3 paired repetitions
- block 내부 순서는 고정 seed로 무작위화하고 repetition마다 fresh process 사용

v5 final의 isolated run은 모두 5초 이상이었다. service-like 일부가 frozen
5초 하한에 미달해 결과를 보고 기준을 바꾸는 대신 amendment v6에서
20초 목표로 전체 service-like cell을 재실행했다. 최종 분석은 isolated
v5와 service-like v6의 비중복 cell만 선택한다. 본 측정 최소 시간은
16.085초였고, 240개 run의 measured elapsed 합계는 약 1.22시간이다.

## v3/v2 paired median 결과

비율 방향은 throughput만 클수록 좋고, 나머지는 작을수록 좋다.

| topology | work | policy | throughput | p99 | CPU/op | peak RSS | gate |
|---|---|---|---:|---:|---:|---:|---|
| isolated | allocator | normalized | 0.988 | 0.501 | 1.013 | 0.546 | PASS |
| isolated | allocator | upstream | 1.016 | 0.697 | 0.990 | 0.695 | PASS |
| isolated | service | normalized | 1.034 | 0.801 | 0.967 | 0.781 | PASS |
| isolated | service | upstream | 1.053 | 0.859 | 0.953 | 0.958 | PASS |
| service-like | allocator | normalized | 1.143 | 0.510 | 0.869 | 0.596 | PASS |
| service-like | allocator | upstream | 0.908 | 1.514 | 1.095 | 1.024 | **FAIL** |
| service-like | service | normalized | 1.013 | 0.494 | 0.982 | 0.461 | PASS |
| service-like | service | upstream | 0.945 | 1.672 | 1.053 | 1.038 | **FAIL** |

gate는 throughput ≥0.97, p99 ≤1.05, CPU/op ≤1.05, peak RSS ≤1.10이며
correctness/provenance/affinity 오류가 없어야 한다. 각 원시 metric의
median, mean, 표준편차, CV, min/max, p25/p75/IQR 및 paired bootstrap
95% CI는 `results/summaries/tcpio-r22-final.json`에 보존했다.

system CPU 비율은 표 순서대로 1.008, 0.957, 0.950, 0.923, 0.902,
1.093, 1.007, 1.018이었다. page fault 비율은 allocator 정책과 THP
동작의 영향을 함께 받으므로 원인으로 단정하지 않으며 raw/summary에
진단 지표로 보존한다. perf hardware counter는 이 r22 run에서 수집하지
않았으므로 unavailable이며 0으로 대체하지 않았다.

## queue-only control과 backpressure

queue-only throughput 비율은 isolated normalized 1.050, isolated upstream
1.013, service-like normalized 0.955, service-like upstream 1.013이었다.
service-like upstream 본 workload의 throughput 저하는 queue-only control
자체에서는 재현되지 않았다. 다만 control은 allocator 결과에서 빼지 않는다.

backpressure는 amendment v4부터 invalid 사유가 아닌 관측 지표다. 모든
pointer의 allocation→policy→origin tcpio→record count/checksum이
일치했고 duplicate/lost/outstanding pointer는 없었다. record bank의
지속 포화, CPU throttling, OOM, swap, host-state drift도 없었다.

## 메모리와 THP 관찰

100 ms RSS/PSS/VmHWM/AnonHugePages 시계열과 cgroup peak를 사용했으며
종료 시점 RSS를 peak로 대체하지 않았다. 선택된 final 240개에서
upstream-default v3의 peak AnonHugePages median은 434,110,464 bytes,
max는 497,025,024 bytes였다. upstream v2와 normalized 양 버전은
median/max가 0이었다. 이는 upstream service-like 실패와 함께 관찰된
상관이며 allocator 기본 정책 하나가 원인이라고 단정할 수 없다.

## 실패·제외·이상치

최종 composite의 invalid run은 0건이다. 이전 r22 amendment v2–v4 결과는
두 개의 orphaned small-queue 컨테이너가 동일 CPU를 약 1시간 점유한 사실을
발견해 전부 성능 근거에서 제외했다. raw 파일은 수정하지 않았고 container
ID와 사유는 `manifests/exclusions-tcpio-r22.json`에 보존했다.

v5 service-like final은 correctness상 valid였지만 5초 최소 duration을
충족하지 않은 run이 있어 최종 service-like 근거에서 제외하고 v6 전체
cell로 교체했다. isolated v5와 service-like v6 repetition은 합산하지 않았다.
재실행 이후에는 컨테이너를 하나씩 순차 실행했고 종료 후 `docker ps`가
비어 있음을 확인했다.

ASAN은 pinned image에 GCC가 요구한 `libasan.so.5.0.0`이 없어 사용자
승인으로 전제에서 제외했다. ASAN을 성공으로 표시하지 않으며 미확인으로
남긴다.

## 결론과 권장사항

이 synthetic pipeline에서는 v3.4.3을 upstream default 그대로 교체하는
gate가 실패했다. 특히 oversubscribed service-like 역할 배치에서 throughput,
p99, CPU/op가 동시에 악화됐다. 반면 normalized 정책은 모든 cell을 통과했다.
따라서 이 배치에 대해서는 host THP와 mimalloc purge/large-page 정책을
명시적으로 고정하고 검증하는 조건으로 v3.4.3 업그레이드를 권장한다.

운영 적용 전에는 실제 payload histogram과 stage work, 로그 서버 지연을
반영한 별도 시험이 필요하다. 단일 NUMA WSL2 결과로 multi-socket,
cross-NUMA 또는 NUMA balancing on/off 효과를 일반화하면 안 된다.

## 재현 명령과 생성물

```bash
python3 scripts/generate_tcpio_r22_plan.py --phase final \
  --calibration config/tcpio-r22e-calibration.json \
  --numa-control-policy disabled-or-kernel-unsupported \
  --isolated-topology record-rebalanced \
  --backpressure-policy metric-only --clean-host-audit \
  --duration-recalibration \
  --output manifests/execution-plan-tcpio-r22e-final.json

bash scripts/container/run_r22.sh normalized service-like \
  manifests/execution-plan-tcpio-r22e-final.json --apply
bash scripts/container/run_r22.sh upstream-default service-like \
  manifests/execution-plan-tcpio-r22e-final.json --apply

python3 scripts/analyze_tcpio_r22.py \
  --isolated-revision tcpio-r22-amendment-v5 \
  --service-like-revision tcpio-r22-amendment-v6 \
  --output results/summaries/tcpio-r22-final.json
```

- frozen v6 plan: `manifests/execution-plan-tcpio-r22e-final.json`
- calibration evidence: `config/tcpio-r22e-calibration.json`
- raw records: `results/raw/r22/`
- stdout/stderr/memory series: `results/logs/r22/`
- machine-readable final summary: `results/summaries/tcpio-r22-final.json`
- exclusion audit: `manifests/exclusions-tcpio-r22.json`
