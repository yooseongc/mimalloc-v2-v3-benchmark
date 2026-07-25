# mimalloc 비교 실험: 코드 분석 기반 정성 보고서

작성일: 2026-07-25  
분석 대상: 이 저장소의 benchmark harness 및 실행·분석 자동화 코드  
정량 결과: [experiment-report.md](experiment-report.md) 및 [한국어 HTML 보고서](experiment-report.ko.html)를 참조

## 범위와 읽는 방법

이 문서는 코드 구조와 실행 통제 방식을 검토한 정성 보고서다. 코드에서 직접 확인할 수 있는 사실과, 최종 측정 결과에서만 말할 수 있는 사실을 구분한다. 즉, 아래의 설계 평가는 특정 allocator가 항상 더 빠르다는 주장이나 원인 확정이 아니다.

최종 정량 비교는 고정된 물리 코어 cpuset과 THP `madvise`/`never` 조건에서 수행됐다. HugeTLB와 cross-NUMA는 사용자 결정으로 미실행이므로, 이 문서는 그 두 항목의 성능 효과를 추정하지 않는다.

## 한눈에 보는 결론

- primary 비교는 하나의 benchmark 바이너리를 유지하고 `LD_PRELOAD`만 바꾸므로, 버전별 benchmark 재빌드가 결과에 섞이는 위험을 낮춘다.
- 실행기는 frozen plan, benchmark SHA-256, allocator library SHA-256, 실제 cpuset, `mi_version`을 차례로 검증한다. 이 검증 실패는 결과를 생성하거나 유효 데이터로 표시하지 않도록 설계돼 있다.
- `local_churn`은 worker별 결과 슬롯과 시작 barrier를 사용해 harness 자체의 공유 상태 경합을 줄인다. `remote_free`는 큐 대기 지표를 출력하고 `queue_only` 대조군을 제공해 allocator 차이와 포인터 전달 비용을 분리해 볼 수 있다.
- 다만 일부 scenario는 worker 내부에서 `std::vector`를 사용하고, 메모리 지표의 `peak_rss_bytes`는 측정 구간의 진정한 peak가 아니라 종료 직후 관측값이다. 이러한 점은 allocator 처리량 외의 영향을 완전히 제거했다는 뜻은 아니다.
- 현 분석은 관측된 차이를 allocator 내부 알고리즘의 인과로 확정하지 않는다. THP 실제 사용량, large-page 실제 부여 여부, perf counter는 별도 진단 수집이 있어야 원인 분석에 활용할 수 있다.

## 1. 비교 대상 고정: 동일 바이너리와 allocator 검증

`benchmark/src/main.cpp`는 시작 시 `detect_allocator()`를 호출하고 mimalloc의 `mi_version` 심볼을 찾지 못하면 종료한다. system allocator로 조용히 fallback한 결과가 섞이는 것을 막는 첫 번째 방어선이다.

```cpp
const AllocatorInfo allocator = detect_allocator();
if (!allocator.mimalloc_detected) {
  std::cerr << "allocator validation failed: mi_version was not resolved\n";
  return 3;
}
```

실행기(`scripts/run_experiment.py`)는 frozen plan의 라이브러리를 `LD_PRELOAD`로 설정한다. 이어서 라이브러리와 benchmark 파일의 SHA-256을 검사한다. timed process가 보고한 라이브러리의 정규화된 경로와 계획의 경로도 다시 비교한다.

```python
env = {"PATH": os.environ["PATH"], "LD_PRELOAD": item["allocator_library_path"]}

if item.get("allocator_library_sha256") and \
        sha256_file(expected_library_file) != item["allocator_library_sha256"]:
    raise SystemExit("refusing: allocator library SHA-256 differs from frozen plan")
if item.get("benchmark_sha256") and \
        sha256_file(expected_benchmark_file) != item["benchmark_sha256"]:
    raise SystemExit("refusing: benchmark SHA-256 differs from frozen plan")
```

이중 검증의 의미는 명확하다. preload를 요청했다는 기록만으로는 부족하고, 실제로 어떤 라이브러리가 로드됐는지와 계획 이후 binary가 변하지 않았는지를 각각 확인한다. r15가 benchmark SHA 불일치로 invalid 감사 기록만 남은 것은 이 정책이 실제로 작동한 사례다.

한계도 있다. `mi_version`은 major 버전 접두어를 확인하는 데 사용되며 tag commit 자체는 frozen plan과 라이브러리 hash로 보장한다. 따라서 library hash와 source/build manifest를 함께 보존하는 현재 방식이 필요하다.

## 2. CPU domain 통제와 worker 배치

현재 process가 볼 수 있는 CPU 집합은 `sched_getaffinity`로 얻는다. worker pinning은 그 집합 안의 CPU만 인자로 받아 `sched_setaffinity`를 호출한다.

```cpp
std::vector<int> current_affinity() {
  cpu_set_t set;
  CPU_ZERO(&set);
  std::vector<int> result;
  if (sched_getaffinity(0, sizeof(set), &set) != 0) return result;
  for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu) {
    if (CPU_ISSET(cpu, &set)) result.push_back(cpu);
  }
  return result;
}
```

`local_churn`의 일반 조건에서는 worker 번호를 allowed CPU 목록의 같은 인덱스에 연결한다. oversubscription만은 의도적으로 modulo mapping을 쓴다.

```cpp
// Oversubscription is an explicit Tier 3 condition: workers round-robin
// through the fixed cpuset instead of silently escaping it.
if (!pin_current_thread(allowed[worker % allowed.size()], error)) std::terminate();
```

이 구현은 worker 수가 cpuset보다 적거나 같은 primary 조건과, worker 수가 더 많은 oversubscription 조건을 같은 CPU domain 안에서 구분한다. 즉 oversubscription 때 OS가 임의의 다른 CPU로 worker를 밀어내는 방식이 아니다.

그러나 이 코드는 pinning 실패 시 `std::terminate()` 한다. 결과는 실패하지만, 실패한 worker의 CPU·오류 문자열을 JSON에 구조화해 남기지는 않는다. 운영상 재현성을 더 높이려면 worker ID, 목표 CPU, `sched_setaffinity` errno를 stderr 및 invalid record에 기록하는 개선이 유용하다.

## 3. local_churn: allocator가 아닌 작업을 줄이려는 구조

`local_churn`은 thread 생성과 affinity 설정을 모두 timed region 이전에 끝낸다. 모든 worker가 준비되면 `ready`를 증가시키고, main thread가 공통 시작 신호를 보낸 후에만 allocation loop로 들어간다.

```cpp
ready.fetch_add(1, std::memory_order_release);
while (!start.load(std::memory_order_acquire)) {}

// main thread
while (ready.load(std::memory_order_acquire) != options.threads) {}
const auto began = std::chrono::steady_clock::now();
start.store(true, std::memory_order_release);
```

worker별 결과는 cache-line alignment를 준 별도 슬롯에 저장한다.

```cpp
struct alignas(64) WorkerResult {
  std::uint64_t checksum{0};
  std::uint64_t allocations{0};
};
```

이는 측정 중 전역 결과 counter를 갱신해 false sharing을 만들 가능성을 줄인다. 포인터에 값을 쓰고 checksum을 누적하는 방식도 compiler가 allocation/free loop를 죽은 코드로 제거하는 위험을 낮춘다.

```cpp
p[0] = static_cast<unsigned char>(i); local.checksum += p[0];
p[size - 1] = static_cast<unsigned char>(i >> 8); local.checksum += p[size - 1];
```

반대로, `std::vector<unsigned char*>`와 size vector는 worker 내부에서 batch마다 `clear()` 후 재사용한다. capacity는 timed region 이전에 `reserve()` 하므로 정상적인 batch 크기에서는 재할당 가능성을 줄인다. 그렇더라도 vector 접근, free-order randomization, touch 방식은 의도적으로 workload에 포함된 harness 비용이다. 따라서 서로 다른 size profile·free order·touch mode의 결과를 하나의 allocator 순위로 합치면 안 된다.

### API 선택의 해석

코드는 `malloc`, C++ `new`, 64-byte aligned allocation, `realloc`을 명시적으로 분기한다.

```cpp
if (options.allocation_api == "cpp-new") {
  p = static_cast<unsigned char*>(::operator new(size));
} else if (options.allocation_api == "aligned") {
  void* raw = nullptr;
  if (posix_memalign(&raw, 64, size) == 0) p = static_cast<unsigned char*>(raw);
} else if (options.allocation_api == "realloc") {
  const std::size_t initial = std::max<std::size_t>(16, size / 2);
  p = static_cast<unsigned char*>(std::malloc(initial));
  if (p != nullptr) p = static_cast<unsigned char*>(std::realloc(p, size));
}
```

따라서 r17은 API 경로별로 의미 있는 보조 비교지만, 기본 `malloc/free` cell과 동일한 workload라고 볼 수 없다. 특히 `realloc`은 half-size에서 target-size로 늘리는 한 방향의 패턴만 다룬다. shrink, in-place 성공률, 서로 다른 alignment 요구는 이 결과의 범위 밖이다.

## 4. remote_free: 큐와 allocator를 분리하려는 시도

`remote_free`에는 bounded MPMC queue가 포함돼 있다. 각 cell이 sequence number를 갖고 enqueue/dequeue position을 atomic compare-exchange로 진전시킨다. producer는 할당한 pointer와 size를 enqueue하고, consumer는 dequeue한 pointer를 free한다.

```cpp
while (!queue.enqueue(value)) full_waits.fetch_add(1, std::memory_order_relaxed);
...
if (!queue.dequeue(value)) {
  empty_waits.fetch_add(1, std::memory_order_relaxed);
  continue;
}
auto* p = static_cast<unsigned char*>(value.pointer);
checksum.fetch_add(p[0] + p[value.size - 1], std::memory_order_relaxed);
std::free(p);
```

보고 JSON에는 `queue_full_wait_count`, `queue_empty_wait_count`, `backpressure_ns`, 전달·해제·outstanding pointer 수가 포함된다. 특히 다음 종료 조건은 모든 pointer가 정확히 한 번 소비됐는지 확인하는 최소 안전장치다.

```cpp
return consumed == total ? 0 : 6;
```

또한 같은 코드 경로에서 `queue_only`를 지원한다. 이 경우에는 실제 allocation 대신 sequence를 pointer 모양의 값으로 전달한다.

```cpp
if (queue_only) {
  value.pointer = reinterpret_cast<void*>(static_cast<std::uintptr_t>(sequence + 1));
  value.size = 0;
}
```

이는 큐 자체의 경합과 allocator의 cross-thread free 비용을 분리하여 관찰하기 위한 좋은 대조군이다. 다만 현재 최종 보고서의 remote-free 결론은 큐 overhead를 수학적으로 빼지 않고 별도 지표로 취급한다. 이것이 올바른 이유는 queue와 allocator의 상호작용 자체가 실제 workload의 일부일 수 있기 때문이다.

개선 후보는 있다. `full_waits`, `empty_waits`, `backpressure_ns`는 모든 producer/consumer가 공유 atomic에 기록한다. 이 기록은 진단상 유용하지만 workload가 아주 작거나 큐 경합이 심한 조건에서는 측정 대상에 추가 경합을 더할 수 있다. 더 엄밀한 latency/queue 분석이 필요하면 worker별 local counter를 두고 종료 후 합산하는 변형을 별도 diagnostic scenario로 제공하는 것이 적절하다.

## 5. 메모리 scenario와 RSS/THP 해석

`memory_scenarios.cpp`가 `lifetime_mix`, `burst_purge`, `thread_churn`, `large_alloc`를 담당한다. 이들은 단순 allocate/free 처리량 외에 객체 수명, idle 구간, thread lifecycle, 큰 객체 touch를 실험하기 위한 분리된 scenario다.

이 분리는 해석의 핵심이다.

- `burst_purge`는 allocator의 release policy와 idle interval의 상호작용을 볼 수 있지만, idle scheduling과 OS reclaim 정책에도 민감하다.
- `thread_churn`은 allocator의 thread-local state 회수뿐 아니라 thread 생성·종료와 scheduler 비용도 포함한다.
- `large_alloc`은 allocator metadata, page fault, zero-fill, touch pattern 및 VM 정책이 함께 반영될 수 있다.

현재 local 및 remote path는 측정 전후 `read_proc_metrics()`를 호출하고 종료 직후 값을 JSON에 넣는다.

```cpp
const ProcMetrics metrics_before = read_proc_metrics();
// measured work
const ProcMetrics metrics_after = read_proc_metrics();
...
"peak_rss_bytes\":" << metrics_after.rss_bytes
```

필드 이름은 `peak_rss_bytes`이지만, 이 코드 경로에서 `metrics_after.rss_bytes`는 실제 실행 중 최대값을 sampling한 것이 아니라 종료 시점 관측값이다. 그러므로 true peak RSS로 해석하려면 scenario 내부의 주기적 sampling 또는 OS가 제공하는 high-water mark와의 교차 확인이 필요하다. 현 보고서에서는 이를 peak memory의 확정 증거로 과장하지 않아야 한다.

THP도 같은 원칙을 적용한다. host의 `madvise`/`never` 설정을 확인하고 r13에서는 저장·적용·복원 절차를 검증했지만, timed process의 `AnonHugePages`를 수집하지 않은 large-page 요청은 실제 large page가 부여됐다는 증거가 아니다.

## 6. 실행 계획: frozen matrix와 쌍 비교

실행기는 임의 YAML을 즉시 해석해 실행하지 않고 `design_status == "Frozen"`인 JSON plan을 요구한다.

```python
plan = json.loads(args.plan.read_text(encoding="utf-8"))
if plan.get("design_status") != "Frozen":
    raise SystemExit("refusing: design_status must be Frozen")
```

각 repetition의 v2/v3 실행은 같은 block으로 묶이고, block의 순서와 block 내부 allocator 순서를 deterministic seed로 섞는다.

```python
block_keys = sorted(blocks)
random.Random(plan["randomization_seed"]).shuffle(block_keys)
for index, key in enumerate(block_keys):
    block = blocks[key]
    random.Random(plan["randomization_seed"] + index + key[1]).shuffle(block)
    entries.extend(block)
```

이 접근은 “v2를 전부 실행한 뒤 v3를 전부 실행”하는 시간 편향을 줄인다. 동일 block의 repetition을 pairing할 수 있으므로 후속 분석도 absolute throughput 평균 대신 paired v3/v2 ratio를 계산할 수 있다.

실행 환경 역시 `PATH`와 `LD_PRELOAD`를 새로 설정하고, plan에 적힌 `MIMALLOC_*` 옵션만 추가한다. 부모 process의 우연한 환경 변수가 결과에 남는 문제를 낮추는 선택이다. 다만 `PATH`는 상속하므로, 장기 재현을 더 강하게 하려면 container image digest와 executable의 절대 경로를 이미 보존하는 현 정책을 유지해야 한다.

## 7. 분석 코드의 장점과 통계적 한계

`scripts/analyze_results.py`는 raw record를 수정하지 않고, 유효 record만 읽어 요약 파일을 생성한다. 중복 key는 제거 목록으로 보존하고, cross-version ratio는 같은 `block_id`와 `repetition`에 v2와 v3가 모두 있을 때만 만든다.

```python
paired.setdefault((row.get("block_id"), row.get("repetition")), {})[
    str(row.get("allocator_version"))
] = row
...
if not v2 or not v3 or not v2.get("elapsed_ns") or not v3.get("elapsed_ns"):
    continue
ratios.append({
    "throughput_ratio_v3_over_v2": v2["elapsed_ns"] / v3["elapsed_ns"],
    "elapsed_ratio_v3_over_v2": v3["elapsed_ns"] / v2["elapsed_ns"],
})
```

이는 legacy raw record나 짝이 없는 실행을 version ratio에 섞지 않는다는 점에서 타당하다. 보고된 비율 방향도 명확하다. 같은 operation count라면 v2 elapsed / v3 elapsed가 1보다 클수록 v3 처리량이 높다.

한편 현재 신뢰구간은 normal approximation이다.

```python
ci_half = 1.96 * stdev / math.sqrt(len(values)) if stdev is not None else None
```

15개 반복에서는 유용한 요약이지만, large allocation처럼 분포가 넓거나 비대칭인 cell에는 이 근사가 충분하지 않을 수 있다. raw repetition을 보존한 현재 구조는 장점이며, 후속 분석에서는 paired log-ratio bootstrap CI 또는 permutation test를 추가하는 편이 더 견고하다. 이는 기존 결론을 바꾸기 위한 소급 조정이 아니라, 이미 고정된 raw data에 대한 추가 민감도 분석으로 다뤄야 한다.

## 8. 정량 결과와 코드 분석을 함께 읽는 법

코드 구조는 아래의 해석을 뒷받침하지만, 인과를 증명하지는 않는다.

| 관측 범주 | 코드가 보장하거나 지원하는 점 | 해석상 금지할 결론 |
|---|---|---|
| local churn | 동시 시작, worker pinning, worker별 결과 축적, checksum | 관측된 차이가 allocator 내부 경로 하나로만 발생했다는 단정 |
| remote free | 실제 다른 worker의 free, 큐 진단 지표, queue-only 대조군 | 큐 비용을 임의로 뺀 값을 allocator 순수 성능이라 부르는 것 |
| THP never | host 상태 저장·적용·복원 절차 | 모든 process가 실제 THP를 사용/미사용했다는 추정 |
| large-page 요청 | 버전별 문서화된 변수 사용 | `AnonHugePages` 확인 없이 page grant를 단정하는 것 |
| r15 제외 | benchmark SHA 불일치 시 실행 거부 | 편의상 해당 record를 최종 ratio에 포함하는 것 |

최종 측정에서는 local fixed-small 8-thread, thread churn 등 일부 cell에 v3 우위가 나타났고, mixed-wide·remote-free의 일부 cell은 동등성 범위를 포함했다. 코드 분석으로부터 가능한 가장 강한 결론은 다음과 같다. 이러한 차이는 고정 binary, 검증된 preload, 고정 cpuset, paired order라는 통제 아래 관측됐지만, page policy·큐 경합·scheduler·touch 비용과 allocator 알고리즘의 상대 기여는 추가 진단 없이는 분리되지 않는다.

## 9. 권장 후속 작업

후속 작업은 최종 결론을 소급 변경하지 않고, 새로운 frozen amendment와 별도 결과 그룹으로 진행해야 한다.

1. true peak RSS가 필요하면 `VmHWM`, cgroup peak, scenario 내부 주기 sampling을 함께 기록하고, 기존 `peak_rss_bytes`의 의미를 `final_observed_rss_bytes`로 명확히 구분한다.
2. THP/large-page 원인을 조사할 때는 timed PID의 `smaps_rollup`, `AnonHugePages`, 관련 `/proc/vmstat` delta를 diagnostic run에 넣는다.
3. remote-free 큐 영향은 worker-local queue 통계 variant와 `queue_only`를 병렬로 수집하되, primary 처리량과 진단 처리량을 같은 표에 합치지 않는다.
4. 분포가 넓은 cell은 paired log-ratio bootstrap CI를 추가해 normal-approximation 결과의 민감도를 확인한다.
5. pinning 실패와 allocator 검증 실패를 JSON invalid record에 구조화된 오류 필드로 남겨 현장 재현을 더 쉽게 한다.
6. NUMA 또는 HugeTLB는 사용자 범위에 포함될 때만, 별도 host 승인·원상 복구·새 frozen plan 아래에서 시행한다.

## 관련 코드와 산출물

- `benchmark/src/main.cpp`: local churn, API 분기, barrier, 결과 JSON
- `benchmark/src/remote_free.cpp`: MPMC queue, remote free, queue-only control
- `benchmark/src/affinity.cpp`: affinity 조회와 worker pinning
- `benchmark/src/memory_scenarios.cpp`: burst/lifetime/thread churn/large allocation
- `scripts/run_experiment.py`: frozen plan 검증, pairing/randomization, preload 및 raw record 생성
- `scripts/analyze_results.py`: immutable raw data 기반 요약과 paired ratio
- `docs/experiment-report.md`: 확정 정량 결과

이 문서는 코드와 확정된 raw-result 처리 절차를 검토한 보고서이며, 소스 수정이나 새로운 benchmark 실행을 수행하지 않았다.
