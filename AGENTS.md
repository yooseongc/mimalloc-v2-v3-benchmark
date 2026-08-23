프로젝트 루트의 `AGENTS.md`로 바로 사용할 수 있는 형태입니다. Codex는 저장소 루트부터 현재 작업 디렉터리까지의 `AGENTS.md`를 계층적으로 읽으며, 기본 합산 한도는 32KiB입니다.

## 0. Active r27 scope override

2026-08-23 사용자 지시에 따라 현재 활성 비교 대상은 다음 세 build다.

* mimalloc `v2.1.2` (`43ce4bd7fd34bcc730c1c7471c99995597415488`)
* mimalloc `v3.5.0` (`18b08671c9302247bfb682286e6bf3cc1773f801`)
* upstream `dev3`를 2026-08-23에 해석한 snapshot
  (`622d421f647fc41a2dfe90bc45174770129d78b4`)

`dev3`는 움직이는 branch를 측정 시점마다 따라가지 않고 위 commit SHA로
고정한다. 이후 branch HEAD가 바뀌면 새 design revision과 result namespace를
만든다. 아래의 v3.4.3 비교 및 moving branch 금지 문구는 r2--r26 historical
epoch 재현에는 계속 적용하지만, 현재 r27 작업과 충돌할 때는 이 절이
우선한다. 활성 계약과 plan은 `experiments/r27-dev3-snapshot-v1/`에 있다.

mimalloc v2.1.2, v3.4.3, v3.5.0은 지원 빌드 옵션, THP 제어, 기본 purge 정책이 다르므로 **기본값 비교**와 **동일 정책 비교**를 분리하도록 구성했습니다. 또한 allocator 벤치마크에서 중요한 동일 스레드 해제, 원격 스레드 해제, 비대칭 producer/consumer, thread churn 패턴을 포함했습니다.

# AGENTS.md

## 1. 프로젝트 목표

이 저장소의 목적은 Microsoft mimalloc의 다음 세 버전을 동일한 Rocky Linux 8 컨테이너 환경에서 재현 가능하게 비교하는 것이다.

* mimalloc `v2.1.2`
* mimalloc `v3.4.3`
* mimalloc `v3.5.0`

주요 비교 대상은 다음과 같다.

1. 동일 스레드에서 할당과 해제를 반복하는 멀티스레드 workload
2. 할당 스레드와 해제 스레드가 다른 remote-free workload
3. 크기 분포, 객체 수명, 스레드 수, NUMA, THP, purge 정책에 따른 변화
4. mimalloc 빌드 옵션과 런타임 옵션에 따른 성능 및 메모리 사용량 변화
5. 처리량뿐 아니라 지연시간, CPU 효율, RSS, 페이지 폴트, OS 메모리 반환 특성 비교

단순히 어느 버전이 더 빠른지 판단하지 말고 다음 질문에 답할 수 있도록 실험한다.

* 어떤 workload에서 v3.4.3과 v3.5.0이 v2.1.2보다 빠르거나 느린가?
* v3.5.0은 v3.4.3보다 어떤 workload에서 개선되거나 회귀하는가?
* cross-thread free 비율에 따라 차이가 어떻게 변하는가?
* 최대 RSS와 해제 후 RSS 감소 특성은 어떻게 다른가?
* THP, NUMA, purge delay가 결과에 얼마나 영향을 주는가?
* 차이가 allocator 자체에서 발생한 것인지 benchmark harness나 OS 환경에서 발생한 것인지 구분할 수 있는가?
* 처리량, tail latency, CPU 사용량, 메모리 사용량 사이에 어떤 trade-off가 있는가?

---

## 2. 필수 산출물

다음 산출물은 반드시 생성해야 한다.

### 2.1 상세 실험 설계서

경로:

```text
docs/experiment-design.md
```

최소 포함 내용:

* 실험 목적
* 비교 대상 버전과 정확한 commit SHA
* 가설
* 독립 변수와 종속 변수
* 통제 변수
* benchmark scenario 정의
* thread topology
* 객체 크기와 수명 분포
* 빌드 설정
* 런타임 환경 변수
* 컨테이너 및 cgroup 구성
* CPU 및 NUMA 배치
* THP 및 HugeTLB 구성
* 실행 순서와 무작위화 방법
* warm-up과 반복 횟수
* 측정 지표
* 통계 분석 방법
* 유효하지 않은 실행의 판정 기준
* 예상 실행 시간과 자원 사용량
* 재현 방법
* 실험의 한계와 validity threat

전체 실험을 시작하기 전에 설계서를 작성한다.

설계서를 확정한 후 다음 정보를 추가한다.

```text
Design status: Frozen
Design revision: <git commit 또는 문서 해시>
Frozen at: <ISO 8601 timestamp>
```

결과를 확인한 뒤 기존 가설이나 제외 기준을 소급해서 변경하지 않는다.

변경이 필요하면 기존 내용을 덮어쓰지 말고 `Amendments` 절에 변경 이유와 시점을 기록한다.

### 2.2 상세 실험 보고서

경로:

```text
docs/experiment-report.md
```

최소 포함 내용:

* Executive summary
* 실험 목적과 범위
* 실험 환경
* 실제 사용된 CPU, 메모리, 커널, glibc, 컴파일러
* 컨테이너 이미지와 digest
* cgroup 설정
* THP, HugeTLB, NUMA 설정
* 세 mimalloc의 tag, commit SHA 및 빌드 옵션
* workload별 결과
* throughput 비교
* latency 비교
* CPU 및 perf counter 비교
* peak RSS 및 메모리 반환 비교
* 통계적 변동성과 신뢰구간
* v3.4.3 / v2.1.2, v3.5.0 / v2.1.2 및 v3.5.0 / v3.4.3 비율
* 이상치 및 실패한 실행
* 제외한 결과와 명확한 제외 이유
* 주요 발견
* workload별 권장사항
* 결과 해석상의 주의점
* 재현 명령
* 원시 데이터와 생성물 위치
* 결론
* 미실행 또는 미확인 항목

실험을 실행하지 못한 경우 결과를 만들어내지 않는다.

그 경우 보고서에 다음과 같이 명확히 표시한다.

```text
Execution status: Not executed
Reason: <실행하지 못한 구체적인 이유>
```

실제 측정되지 않은 수치, 그래프 또는 결론을 절대로 생성하지 않는다.

---

## 3. 권장 저장소 구조

다음과 유사한 구조를 만든다.

```text
.
├── AGENTS.md
├── README.md
├── Makefile
├── CMakeLists.txt
├── container/
│   ├── Dockerfile
│   ├── image.lock
│   └── entrypoint.sh
├── benchmark/
│   ├── CMakeLists.txt
│   ├── include/
│   ├── src/
│   │   ├── main.cpp
│   │   ├── allocator_detector.cpp
│   │   ├── affinity.cpp
│   │   ├── local_churn.cpp
│   │   ├── remote_free.cpp
│   │   ├── lifetime_mix.cpp
│   │   ├── burst_purge.cpp
│   │   ├── thread_churn.cpp
│   │   └── large_alloc.cpp
│   └── tests/
├── config/
│   ├── experiment.yaml
│   ├── smoke.yaml
│   ├── core.yaml
│   └── extended.yaml
├── manifests/
│   ├── sources.lock
│   ├── builds.json
│   └── environment.json
├── scripts/
│   ├── fetch_sources.sh
│   ├── build_mimalloc.sh
│   ├── build_benchmark.sh
│   ├── collect_environment.sh
│   ├── validate_environment.sh
│   ├── smoke_test.sh
│   ├── run_experiment.py
│   ├── analyze_results.py
│   ├── generate_report.py
│   ├── container/
│   │   ├── build.sh
│   │   └── run.sh
│   └── host/
│       ├── inspect_host.sh
│       ├── set_thp.sh
│       ├── set_numa_balancing.sh
│       └── restore_host.sh
├── extern/
│   └── .gitkeep
├── build/
│   └── .gitkeep
├── results/
│   ├── README.md
│   ├── raw/
│   ├── normalized/
│   ├── summaries/
│   ├── plots/
│   └── logs/
├── docs/
│   ├── experiment-design.md
│   └── experiment-report.md
├── requirements.txt
└── .gitignore
```

`extern/`, `build/`, 대용량 raw result는 기본적으로 Git에 포함하지 않는다.

실험 설계서, 보고서, 설정 파일, source/build manifest, 집계 결과와 재현에 필요한 스크립트는 Git에 포함한다.

---

## 4. 작업 순서

다음 순서를 지킨다.

1. 요구사항과 upstream 자료 조사
2. 상세 실험 설계서 초안 작성
3. 저장소 구조 및 benchmark harness 구현
4. 컨테이너와 빌드 자동화 구현
5. 환경 수집 및 검증 도구 구현
6. 단위 테스트 및 correctness test 수행
7. smoke benchmark 수행
8. pilot benchmark 수행
9. 설계서와 실행 matrix 확정
10. core benchmark 수행
11. extended benchmark 수행
12. 데이터 정규화 및 통계 분석
13. 그래프와 표 생성
14. 상세 실험 보고서 작성
15. 전체 재현 절차 검증

설계와 구현을 동시에 무계획하게 확장하지 않는다.

실험 matrix가 너무 커지면 다음 단계로 나눈다.

* Tier 0: correctness 및 smoke
* Tier 1: 핵심 성능 비교
* Tier 2: THP, purge, NUMA 분석
* Tier 3: 빌드 옵션 및 추가 workload

각 단계의 예상 실행 시간을 계산해 설계서에 기록한다.

---

## 5. upstream source 관리

### 5.1 정확한 버전 사용

반드시 다음 tag를 사용한다.

```text
microsoft/mimalloc v2.1.2
microsoft/mimalloc v3.4.3
microsoft/mimalloc v3.5.0
```

`main`, `master`, `dev`, `dev2`, `dev3` 또는 움직이는 branch를 비교 대상으로 사용하지 않는다.

각 source에 대해 다음 정보를 기록한다.

```text
repository
requested tag
resolved commit SHA
git describe
fetch timestamp
source directory
source tree status
```

실제 commit SHA는 다음 파일에 고정한다.

```text
manifests/sources.lock
```

예시 형식:

```yaml
mimalloc:
  v2.1.2:
    repository: microsoft/mimalloc
    tag: v2.1.2
    commit: "<resolved SHA>"
  v3.4.3:
    repository: microsoft/mimalloc
    tag: v3.4.3
    commit: "<resolved SHA>"
  v3.5.0:
    repository: microsoft/mimalloc
    tag: v3.5.0
    commit: "18b08671c9302247bfb682286e6bf3cc1773f801"
```

### 5.2 upstream source 수정 금지

primary benchmark에서는 upstream mimalloc source를 수정하지 않는다.

수정이 꼭 필요한 경우:

* 수정 이유를 문서화한다.
* patch를 별도 파일로 보관한다.
* 원본 결과와 patch 적용 결과를 분리한다.
* patch 적용 결과를 공식 버전 결과처럼 표현하지 않는다.

### 5.3 build 분리

세 버전의 source, build, install prefix를 완전히 분리한다.

예:

```text
extern/mimalloc-v2.1.2/
extern/mimalloc-v3.4.3/
extern/mimalloc-v3.5.0/

build/mimalloc-v2.1.2/<profile>/
build/mimalloc-v3.4.3/<profile>/
build/mimalloc-v3.5.0/<profile>/

opt/mimalloc-v2.1.2/<profile>/
opt/mimalloc-v3.4.3/<profile>/
opt/mimalloc-v3.5.0/<profile>/
```

동일한 이름의 shared library가 서로 덮어써지지 않게 한다.

---

## 6. 컨테이너 환경

### 6.1 기본 이미지

Rocky Linux 8 기반 OCI 컨테이너를 사용한다.

가능하면 base image를 digest로 고정하고 다음 정보를 기록한다.

* image name
* image digest
* 설치된 RPM 전체 목록
* GCC/G++ 버전
* CMake 버전
* glibc 버전
* binutils 버전
* Python 버전
* perf 버전

최초 image pull 이후 실제 digest를 다음 파일에 기록한다.

```text
container/image.lock
```

`latest`나 움직이는 tag만 기록해서는 안 된다.

### 6.2 동일 컨테이너 사용

두 mimalloc 버전은 반드시 동일한 container image에서 빌드하고 실행한다.

다음 항목이 두 버전 사이에서 달라지면 안 된다.

* compiler
* compiler flags
* linker
* glibc
* kernel
* container image
* cpuset
* memory limit
* NUMA memory node
* benchmark binary
* workload seed
* operation count
* queue capacity
* warm-up
* 반복 횟수

### 6.3 네트워크

dependency와 source를 모두 준비한 후 실제 측정 실행은 가능하면 다음 조건에서 수행한다.

```text
network disabled
no package installation
no source download
no background updater
```

측정 중 네트워크 다운로드를 수행하지 않는다.

---

## 7. CPU와 cgroup 통제

### 7.1 cpuset을 우선 사용

CPU 수를 제한할 때 `--cpus` quota만 사용하지 않는다.

primary benchmark에서는 고정된 논리 CPU 목록을 사용하는 cpuset을 설정한다.

예:

```text
--cpuset-cpus=<fixed CPU list>
```

필요한 경우 다음도 설정한다.

```text
--cpuset-mems=<fixed NUMA node>
```

두 버전은 정확히 동일한 CPU 목록을 사용해야 한다.

### 7.2 affinity 검증

실행 전후 다음을 수집하고 예상값과 비교한다.

* `/proc/self/status`의 `Cpus_allowed_list`
* `sched_getaffinity`
* cgroup v2의 `cpuset.cpus.effective`
* cgroup v1의 cpuset 설정
* `nproc`
* worker별 실제 CPU 배치

affinity가 예상과 다르면 해당 실행은 invalid 처리한다.

### 7.3 worker pinning

benchmark worker는 명시적으로 CPU에 pinning한다.

primary benchmark에서는 다음 원칙을 사용한다.

* 한 worker당 하나의 논리 CPU
* 같은 physical core의 SMT sibling은 기본 matrix에서 동시에 사용하지 않음
* 같은 NUMA node의 physical core를 우선 사용
* worker ID와 CPU ID 매핑을 결과에 기록
* allocator 버전에 따라 worker 배치를 바꾸지 않음

SMT 포함 실험은 별도 extended scenario로 분리한다.

### 7.4 CPU quota와 throttling

가능하면 cpuset만 사용하고 CPU quota throttling은 사용하지 않는다.

quota를 사용해야 한다면 두 버전에 동일하게 적용하고 다음을 매 실행마다 기록한다.

* `cpu.stat`
* throttled time
* `nr_throttled`
* quota
* period

측정 구간 중 CPU throttling이 발생하면 해당 실행을 invalid로 표시한다.

### 7.5 CPU frequency와 host load

다음을 수집한다.

* CPU model
* microcode
* governor
* turbo/boost 상태
* nominal frequency
* 측정 중 평균 frequency
* host load
* steal time
* 온도 정보가 노출되는 경우 CPU 온도

설정을 변경할 수 없으면 변경하지 말고 uncontrolled variable로 보고서에 기록한다.

---

## 8. NUMA 통제

다음을 수집한다.

```text
lscpu -e
numactl --hardware
numastat
/proc/sys/kernel/numa_balancing
/proc/<pid>/numa_maps
```

primary benchmark 기본 조건은 다음과 같다.

* worker CPU를 하나의 NUMA node에 배치
* memory allocation도 같은 NUMA node에 bind
* 두 버전의 CPU와 memory node를 동일하게 유지

다음은 별도 extended experiment로 분리한다.

* single-node CPU + single-node memory
* single-node CPU + interleaved memory
* cross-node CPU
* NUMA balancing enabled
* NUMA balancing disabled
* `MIMALLOC_USE_NUMA_NODES=1`
* 실제 NUMA node 수 사용

NUMA balancing이나 memory policy를 host에서 변경할 때는 일반 실행 스크립트가 임의로 변경해서는 안 된다.

반드시 `scripts/host/` 아래의 별도 스크립트로 수행하고 원래 값을 저장한 뒤 복원할 수 있어야 한다.

---

## 9. THP와 Huge Page 통제

다음 세 개념을 혼동하지 않는다.

1. Linux Transparent Huge Pages
2. 명시적인 large OS page 사용
3. 사전 예약한 HugeTLB 1GiB page

각 실행 전에 다음을 기록한다.

```text
/sys/kernel/mm/transparent_hugepage/enabled
/sys/kernel/mm/transparent_hugepage/defrag
/sys/kernel/mm/transparent_hugepage/shmem_enabled
/proc/meminfo의 HugePages 관련 값
/proc/vmstat의 thp_* 값
/proc/<pid>/smaps_rollup
/proc/<pid>/status
/proc/<pid>/numa_maps
```

THP 설정 문자열만 보고 THP가 실제 사용되었다고 판단하지 않는다.

다음 지표로 실제 사용을 확인한다.

* `AnonHugePages`
* `FilePmdMapped`
* `ShmemPmdMapped`
* `THPeligible`
* `thp_fault_alloc`
* `thp_collapse_alloc`
* `thp_split_page`
* `thp_deferred_split_page`

### 9.1 공통 THP 비교

두 버전이 공통으로 영향을 받는 host THP 상태를 우선 비교한다.

최소 조건:

```text
THP=never
THP=madvise
```

자원이 허용되면 다음도 추가한다.

```text
THP=always
```

THP 상태별 실험은 별도 block으로 실행한다.

### 9.2 버전 전용 옵션

특정 버전에만 존재하는 THP build/runtime option은 primary cross-version 결과에 섞지 않는다.

다음 두 종류의 결과를 구분한다.

* 공통 조건에서의 v2 대 v3 비교
* v3 전용 설정의 내부 비교

지원하지 않는 CMake 옵션을 다른 버전에 전달하지 않는다.

### 9.3 host 설정 변경 안전성

THP, HugeTLB, NUMA balancing과 같은 host-wide 설정은 다음 조건을 지킨다.

* 현재 상태를 먼저 출력
* 현재 상태를 파일에 저장
* 명시적인 `--apply` 없이는 변경하지 않음
* 종료 또는 오류 시 원상 복구
* 운영 서버에서는 실행하지 않음
* 권한 부족 시 실패 이유를 명확히 출력
* 변경하지 못했는데 변경되었다고 가정하지 않음

---

## 10. mimalloc 빌드 정책

### 10.1 두 종류의 비교를 분리

다음 두 비교를 모두 지원한다.

#### A. Upstream-default comparison

각 버전의 Release 기본 동작을 최대한 유지한다.

목적:

* 사용자가 각 버전을 기본 설정으로 사용할 때의 실제 차이 확인
* 버전별 기본 정책 변경의 효과 포함

#### B. Normalized-policy comparison

두 버전에서 의미상 동일하게 맞출 수 있는 옵션과 환경 변수만 동일하게 설정한다.

목적:

* 서로 다른 기본값의 영향을 줄이고 allocator 구현 차이에 가까운 비교 수행

두 결과를 하나의 표에서 무분별하게 섞지 않는다.

### 10.2 공통 Release baseline

가능한 공통 baseline:

```text
CMAKE_BUILD_TYPE=Release
CMAKE_C_COMPILER=<same compiler>
CMAKE_C_FLAGS_RELEASE="-O3 -DNDEBUG"
MI_OVERRIDE=ON
MI_BUILD_SHARED=ON
MI_BUILD_STATIC=OFF
MI_BUILD_OBJECT=OFF
MI_BUILD_TESTS=OFF
MI_SECURE=OFF
MI_LOCAL_DYNAMIC_TLS=OFF
MI_TRACK_VALGRIND=OFF
MI_TRACK_ASAN=OFF
MI_DEBUG_TSAN=OFF
MI_DEBUG_UBSAN=OFF
MI_SHOW_ERRORS=OFF
```

실제로 각 tag가 지원하는 옵션인지 CMakeLists.txt에서 확인한 후에만 전달한다.

지원하지 않는 옵션을 전달하고 CMake가 무시하게 두지 않는다.

### 10.3 버전별 옵션 manifest

각 build에 대해 다음을 저장한다.

* 전체 CMake command
* `CMakeCache.txt`
* compiler flags
* linker flags
* compile command
* generated shared library 경로
* shared library SHA-256
* installed header SHA-256
* resolved mimalloc commit SHA
* build timestamp

경로:

```text
manifests/builds.json
```

### 10.4 build option 실험

모든 옵션을 full factorial로 조합하지 않는다.

baseline을 기준으로 한 번에 하나의 변수만 바꾸는 방식으로 분석한다.

공통 비교 후보:

* `MI_SECURE`
* `MI_LOCAL_DYNAMIC_TLS`
* purge delay
* arena eager commit
* explicit large OS page
* HugeTLB reservation
* NUMA node 제한

특정 버전에만 존재하는 옵션은 버전 내부 비교로 분리한다.

예:

* architecture-specific optimization
* SIMD 최적화
* v3 전용 THP 제어
* v3 전용 secure-full
* v3 전용 guarded mode

debug, ASAN, TSAN, UBSAN build는 correctness 진단용이며 Release 성능 결과에 포함하지 않는다.

---

## 11. allocator 주입 방식

### 11.1 동일 benchmark binary 사용

primary cross-version 비교에서는 동일한 benchmark executable을 사용한다.

benchmark는 C++17로 작성하되 primary allocation API는 다음을 사용한다.

```cpp
std::malloc
std::free
std::realloc
```

allocator는 `LD_PRELOAD`로 교체한다.

benchmark executable 자체를 mimalloc 버전별로 다시 빌드하지 않는다.

benchmark compiler에는 필요할 경우 다음 최적화 방지 옵션을 사용한다.

```text
-fno-builtin-malloc
-fno-builtin-free
-fno-builtin-realloc
```

### 11.2 allocator 검증

각 실행 전 실제 allocator가 올바르게 로드되었는지 검증한다.

검증 방법:

* `/proc/<pid>/maps`
* 로드된 shared library 절대 경로
* shared library SHA-256
* `dlsym`을 통한 `mi_version` 탐지
* 별도 validation run에서 verbose 정보 확인

다음 중 하나라도 불일치하면 실행을 중단한다.

* 요청 버전과 탐지 버전 불일치
* 예상하지 않은 mimalloc library 로드
* 두 mimalloc library가 동시에 로드됨
* system allocator로 fallback
* install prefix 혼합

verbose 또는 loader debug 출력은 validation run에서만 사용한다.

timed run에서는 상세 로그를 비활성화한다.

### 11.3 추가 API 비교

다음은 secondary scenario로만 추가한다.

* C++ `new/delete`
* aligned allocation
* `realloc`
* mimalloc 직접 API
* STL allocator

직접 API 결과를 `LD_PRELOAD + malloc/free` 결과와 같은 데이터처럼 취급하지 않는다.

---

## 12. benchmark harness 요구사항

benchmark harness는 C++17로 작성한다.

### 12.1 timed region

다음 작업은 timed region 밖에서 수행한다.

* 설정 파일 파싱
* thread 생성
* CPU affinity 설정
* size sequence 생성
* queue allocation
* result buffer allocation
* 로그 파일 열기
* allocator validation
* warm-up

다만 thread 생성 비용을 측정하는 `thread_churn` scenario는 예외다.

### 12.2 동기화

모든 worker가 준비된 뒤 동일한 barrier에서 시작한다.

* 준비 barrier
* 측정 시작 시각
* 측정 종료 barrier
* worker별 완료 확인

worker마다 서로 다른 시작 시각으로 측정하지 않는다.

### 12.3 workload 고정

시간 제한 동안 최대한 많이 수행하는 방식만 사용하지 않는다.

primary 결과는 동일한 operation count를 수행하고 elapsed time을 비교한다.

pilot run에서 목표 실행 시간이 되도록 operation count를 보정한 뒤 해당 값을 두 버전에서 동일하게 사용한다.

권장 measured duration:

```text
최소 5초
권장 10~30초
```

너무 짧아 startup noise가 결과를 지배하지 않게 한다.

### 12.4 optimizer 방지

컴파일러가 allocation이나 memory access를 제거하지 못하게 한다.

* 반환 포인터 사용
* deterministic checksum 계산
* 객체에 실제 값 기록
* 최종 checksum 출력
* 모든 allocation이 실제로 해제되었는지 검증

`volatile`을 무분별하게 사용하지 않는다.

### 12.5 false sharing 방지

benchmark harness 자체가 allocator보다 큰 contention을 만들지 않게 한다.

* worker별 counter를 cache line 단위로 분리
* producer/consumer queue의 head와 tail 분리
* thread-local 통계 사용
* timed region 내 글로벌 mutex 금지
* timed region 내 로그 출력 금지
* 결과 집계는 측정 이후 수행

### 12.6 latency sampling

모든 단일 allocation을 개별 timestamp로 측정해 측정 오버헤드가 workload를 지배하게 하지 않는다.

다음 중 하나를 사용한다.

* batch latency
* 일정 간격 sampling
* 별도 latency-focused run

sampling 비율과 overhead를 문서화한다.

---

## 13. 필수 benchmark scenario

### 13.1 `local_churn`

각 worker가 직접 할당하고 같은 worker가 해제한다.

변수:

* thread count
* object size profile
* batch size
* allocation/free order
* touch mode
* outstanding object count

최소 패턴:

1. allocate one, free one
2. batch allocate, batch free FIFO
3. batch allocate, batch free LIFO
4. randomized free order

최소 size profile:

```text
fixed-small: 64 B
fixed-medium: 4 KiB
mixed-small: 16 B ~ 4 KiB
mixed-wide: 16 B ~ 64 KiB
```

size distribution은 명확하게 정의하고 seed를 고정한다.

### 13.2 `remote_free`

한 thread가 할당한 객체를 다른 thread가 해제한다.

최소 topology:

```text
1 producer : 1 consumer
N producers : N consumers
1 producer : N consumers
N producers : 1 consumer
```

primary topology는 사용 가능한 CPU 수에 맞춰 producer와 consumer를 동일 NUMA node에 균등 배치한다.

다음을 기록한다.

* producer 수
* consumer 수
* queue capacity
* queue occupancy
* full wait count
* empty wait count
* backpressure time
* 전송된 pointer 수
* 해제된 pointer 수
* outstanding pointer 수

모든 pointer가 정확히 한 번 해제되었는지 검증한다.

queue 성능이 allocator 차이를 가리지 않는지 확인하기 위해 동일한 pointer 전달만 수행하는 `queue_only` control을 제공한다.

queue overhead를 allocator 결과에서 임의로 빼지 말고 별도 지표로 보고한다.

### 13.3 `lifetime_mix`

서로 다른 객체 수명을 섞는다.

예:

* 70% short-lived
* 20% medium-lived
* 10% long-lived

비율과 실제 retention depth를 설정 파일에 기록한다.

long-lived 객체가 여러 cycle을 지나 살아남도록 한다.

### 13.4 `burst_purge`

다음 cycle을 반복한다.

1. target working set까지 할당
2. 모든 page를 실제 touch
3. 일부 또는 전체 해제
4. 정해진 시간 동안 idle
5. RSS와 page 상태 측정
6. 다음 burst 수행

idle interval 예:

```text
0 ms
10 ms
100 ms
1000 ms
5000 ms
```

측정 항목:

* burst allocation latency
* free latency
* peak RSS
* free 직후 RSS
* idle 이후 RSS
* 다음 burst latency
* minor/major fault
* `madvise` 관련 진단 지표
* THP 사용량

### 13.5 `thread_churn`

worker thread를 반복해서 생성하고 종료한다.

일부 객체는 allocating thread보다 오래 살아남고 다른 thread에서 해제되게 한다.

측정 항목:

* thread cycle 시간
* cycle별 RSS
* 종료 후 남은 RSS
* abandoned/reclaimed memory 관련 allocator 통계
* page fault
* context switch

### 13.6 `large_alloc`

다음 크기 범위를 포함한다.

```text
64 KiB
256 KiB
1 MiB
2 MiB
4 MiB
16 MiB
64 MiB
```

THP 및 large page 실험에서는 page 전체를 touch하는 mode를 사용한다.

allocator metadata 성능과 순수 메모리 bandwidth가 혼합되지 않도록 touch mode별 결과를 분리한다.

---

## 14. thread count matrix

실제 사용 가능한 physical core 수를 `P`라고 한다.

기본 thread sweep:

```text
1
2
4
8
P
```

`P`보다 큰 값은 생략한다.

remote-free scenario에서는 producer와 consumer의 합이 할당된 CPU 수를 넘지 않게 한다.

oversubscription 실험은 별도 extended test로 분리한다.

thread count별로 실제 CPU mapping을 결과에 저장한다.

---

## 15. 메모리 접근 mode

다음 mode를 분리한다.

```text
none
first-byte
first-and-last
per-cache-line
per-page
full-write
```

primary allocator throughput에서는 `first-and-last`를 기본 후보로 사용한다.

THP, RSS, page fault 실험에서는 `per-page` 또는 `full-write`를 사용한다.

서로 다른 touch mode 결과를 직접 합산하지 않는다.

---

## 16. 런타임 정책 비교

### 16.1 기본 정책 비교

각 버전의 upstream runtime default를 그대로 둔 결과를 별도로 측정한다.

결과 이름에 반드시 다음을 표시한다.

```text
policy=upstream-default
```

### 16.2 동일 정책 비교

두 버전 모두 지원하며 의미가 대응되는 설정만 사용한다.

최소 비교 후보:

```text
purge_delay=0
purge_delay=1000
purge_delay=-1
arena_eager_commit=0
arena_eager_commit=1
numa_nodes=1
large_os_pages=0
large_os_pages=1
```

한 번에 여러 변수를 함께 변경하지 않는다.

`upstream-default`와 명시적으로 설정한 값은 구분한다.

환경 변수가 설정되지 않은 상태를 숫자 기본값과 동일하다고 간주하지 않는다.

### 16.3 통제 환경 변수

각 실행의 전체 `MIMALLOC_*` 환경 변수를 raw result에 기록한다.

이전 실행의 환경 변수가 다음 실행에 남지 않도록 clean environment에서 실행한다.

예상하지 않은 `MIMALLOC_*` 변수가 존재하면 실행을 중단한다.

---

## 17. 실행 단계

### 17.1 Tier 0: correctness와 smoke

목적:

* build 확인
* 올바른 allocator load 확인
* crash, hang, double free 확인
* 결과 형식 확인
* affinity 확인
* checksum 확인
* 모든 pointer 해제 확인

짧은 실행으로만 수행한다.

smoke 결과를 최종 성능 결론에 사용하지 않는다.

### 17.2 Pilot

각 핵심 cell에 대해 최소 3회 실행한다.

pilot에서 확인할 항목:

* 목표 실행 시간
* workload stability
* queue bottleneck
* RSS limit
* CPU throttling
* 결과 분산
* perf 사용 가능 여부
* 전체 예상 실행 시간

pilot 결과로 operation count를 확정하되 두 버전에 동일하게 적용한다.

### 17.3 Tier 1: core comparison

최소 포함:

* `local_churn`
* `remote_free`
* fixed-small
* mixed-wide
* thread 1
* 최대 physical core
* 동일 NUMA node
* THP 고정 상태
* normalized runtime policy
* v2.1.2
* v3.4.3

### 17.4 Tier 2: memory policy

최소 포함 후보:

* THP never/madvise
* purge delay
* burst/idle
* lifetime mix
* thread churn
* large allocation
* peak RSS
* RSS 반환 속도

### 17.5 Tier 3: extended comparison

자원이 허용될 때만 수행한다.

* upstream defaults
* local dynamic TLS
* secure build
* explicit large OS page
* HugeTLB
* NUMA balancing
* cross-NUMA
* SMT
* oversubscription
* v3 전용 옵션
* C++ new/delete
* aligned allocation
* realloc

---

## 18. 반복, 순서 무작위화 및 안정화

### 18.1 warm-up

각 measured run 전에 동일한 warm-up을 수행한다.

warm-up operation은 measured operation과 분리해 기록한다.

### 18.2 반복 횟수

각 core cell은 최소 15개의 valid measured repetition을 확보한다.

pilot 결과의 coefficient of variation이 높으면 30회까지 늘린다.

반복 횟수를 줄여야 하면 이유를 보고서에 기록한다.

### 18.3 block randomization

동일한 scenario/config에서 v2와 v3를 하나의 비교 block으로 묶는다.

block 내부 실행 순서는 seed 기반으로 무작위화한다.

예:

```text
Block 1: v2, v3
Block 2: v3, v2
Block 3: v3, v2
Block 4: v2, v3
```

모든 v2 실행 후 모든 v3 실행을 수행하지 않는다.

시간 경과, 온도, host 상태 변화가 특정 버전에 편향되지 않게 한다.

randomization seed를 manifest에 기록한다.

### 18.4 fresh process

각 repetition은 새로운 benchmark process에서 수행한다.

allocator state가 다음 repetition으로 이어지지 않게 한다.

단, 지속 실행 중 RSS 변화를 분석하는 scenario는 예외이며 별도로 표시한다.

---

## 19. 수집 지표

### 19.1 primary metrics

* elapsed time
* operations per second
* nanoseconds per operation
* allocations per second
* frees per second
* peak RSS
* measured-region RSS 변화
* user CPU time
* system CPU time

### 19.2 latency

가능하면 다음을 보고한다.

* p50
* p90
* p95
* p99
* p99.9
* maximum
* batch latency
* latency sample count

### 19.3 perf counters

사용 가능한 경우 다음을 수집한다.

```text
task-clock
cycles
instructions
IPC
branches
branch-misses
cache-references
cache-misses
L1-dcache-loads
L1-dcache-load-misses
LLC-loads
LLC-load-misses
context-switches
cpu-migrations
page-faults
minor-faults
major-faults
```

perf 권한이 없으면 실패를 숨기지 말고 unavailable로 기록한다.

성능 실행에 필요한 권한을 얻기 위해 과도한 container privilege를 기본값으로 요구하지 않는다.

### 19.4 메모리

* VmRSS
* VmHWM
* VmSize
* RssAnon
* RssFile
* PSS
* private dirty
* anonymous huge pages
* cgroup memory current
* cgroup peak memory
* swap 사용량
* minor/major faults
* NUMA node별 memory

cgroup v1과 v2를 모두 탐지해서 대응한다.

지원되지 않는 지표를 0으로 기록하지 말고 null 또는 unavailable로 기록한다.

### 19.5 진단 지표

별도 diagnostic run에서 다음을 수집할 수 있다.

* mimalloc statistics
* `/proc/<pid>/smaps`
* syscall count
* mmap/munmap/madvise count
* allocator verbose output
* strace
* perf record

진단 도구의 overhead가 큰 실행을 primary throughput 결과에 포함하지 않는다.

---

## 20. raw result 형식

각 repetition은 독립된 JSON 또는 JSONL record로 저장한다.

최소 필드:

```text
experiment_id
run_id
block_id
timestamp
valid
invalid_reason
allocator_name
allocator_version
allocator_commit
allocator_library_path
allocator_library_sha256
build_profile
scenario
thread_count
producer_count
consumer_count
cpu_list
numa_nodes
size_profile
touch_mode
operation_count
warmup_count
seed
runtime_options
thp_mode
hugepage_mode
elapsed_ns
operations_per_second
latency_percentiles
user_cpu_seconds
system_cpu_seconds
peak_rss_bytes
final_rss_bytes
page_faults
perf_counters
cgroup_before
cgroup_after
environment_manifest_hash
design_revision
checksum
exit_code
stdout_path
stderr_path
```

raw result는 생성 후 수정하지 않는다.

정규화, 제외 판정, 파생 지표는 별도 파일에 작성한다.

---

## 21. 통계 분석

평균만 보고하지 않는다.

각 cell에 대해 최소한 다음을 보고한다.

* valid repetition 수
* invalid repetition 수
* median
* mean
* standard deviation
* coefficient of variation
* minimum
* maximum
* p25
* p75
* IQR
* 95% confidence interval

v3 대 v2 비교는 가능한 한 동일 block의 paired result를 사용한다.

다음 비율을 명시한다.

```text
throughput ratio = v3 / v2
elapsed ratio = v3 / v2
peak RSS ratio = v3 / v2
CPU time ratio = v3 / v2
```

비율의 방향을 표와 그래프에 명확하게 표시한다.

예:

```text
throughput ratio > 1: v3가 더 높은 처리량
elapsed ratio < 1: v3가 더 짧은 실행시간
RSS ratio < 1: v3가 더 적은 메모리 사용
```

paired log ratio에 대한 bootstrap 95% confidence interval을 기본 분석 후보로 사용한다.

여러 workload를 하나의 종합 비율로 요약할 때는 arithmetic mean 대신 geometric mean을 사용한다.

통계적 유의성만으로 실질적 성능 차이라고 결론 내리지 않는다.

effect size와 측정 변동성을 함께 보고한다.

---

## 22. 이상치 및 invalid run 처리

결과를 보기 좋게 만들기 위해 이상치를 임의 제거하지 않는다.

허용되는 invalid 사유를 설계서에 사전 정의한다.

예:

* benchmark crash
* checksum mismatch
* pointer leak
* wrong allocator loaded
* affinity mismatch
* CPU throttling 발생
* OOM kill
* container resource 설정 불일치
* host THP 상태 불일치
* signal에 의한 종료
* 결과 파일 손상
* operation count 불일치

성능이 단순히 느리거나 빠르다는 이유는 제외 사유가 아니다.

invalid raw result도 삭제하지 않는다.

보고서에 전체 invalid 수와 사유를 표로 제공한다.

---

## 23. 환경 검증

실행 전 다음을 자동 검사한다.

* Rocky Linux 8 container인지
* 두 allocator source의 commit SHA가 lock과 일치하는지
* benchmark binary SHA가 예상과 일치하는지
* build profile이 예상과 일치하는지
* CPU allowed list가 예상과 일치하는지
* NUMA memory policy가 예상과 일치하는지
* cgroup CPU와 memory 설정이 동일한지
* THP 상태가 config와 일치하는지
* swap 설정이 예상과 일치하는지
* 올바른 allocator library가 preload되는지
* 예상하지 않은 mimalloc 환경 변수가 없는지
* 결과 디렉터리에 충돌하는 run ID가 없는지

검증 실패 시 benchmark를 계속 실행하지 않는다.

---

## 24. 테스트 요구사항

benchmark harness에 다음 테스트를 작성한다.

### Unit tests

* size generator reproducibility
* workload seed reproducibility
* percentile calculation
* checksum calculation
* JSON serialization
* configuration validation
* CPU list parsing
* cgroup v1/v2 parsing
* allocator version parsing

### Correctness tests

* allocation count와 free count 일치
* remote-free pointer exactly-once 해제
* queue overflow/underflow 처리
* 모든 worker 정상 종료
* outstanding allocation 0
* size와 alignment 만족
* invalid config 거부
* allocator load 검증 실패 처리

### Integration tests

* v2.1.2 build
* v3.4.3 build
* system allocator smoke
* v2 preload smoke
* v3 preload smoke
* local churn smoke
* remote free smoke
* raw result 생성
* analysis script 실행
* report 생성

---

## 25. 자동화 명령

최종 저장소는 최소한 다음 인터페이스를 제공한다.

```bash
make image
make fetch
make build
make test
make validate
make smoke
make pilot
make benchmark-core
make benchmark-extended
make analyze
make report
make all
```

각 target은 실패 시 non-zero로 종료한다.

`make benchmark-core`는 design이 frozen되지 않았으면 실행을 거부해야 한다.

`make report`는 raw data가 없으면 측정 결과를 생성하지 않고 미실행 상태의 보고서를 생성한다.

README에는 처음부터 끝까지 재현 가능한 명령을 제공한다.

---

## 26. 그래프 요구사항

최소한 다음 그래프를 생성한다.

* throughput versus thread count
* v3/v2 throughput ratio
* elapsed-time ratio
* peak RSS versus thread count
* v3/v2 RSS ratio
* latency percentile comparison
* throughput versus allocation size
* remote-free topology comparison
* purge 후 RSS time series
* THP mode comparison
* CPU cycles per operation
* instructions per operation
* cache miss per operation

각 그래프에 다음을 표시한다.

* allocator version
* scenario
* thread count
* size profile
* THP mode
* runtime policy
* repetition 수
* confidence interval 또는 dispersion
* 단위
* ratio 방향

축을 잘라 차이를 과장하지 않는다.

raw value와 normalized ratio를 모두 제공한다.

---

## 27. 보고서 해석 규칙

다음과 같은 단순 결론을 피한다.

```text
v3가 항상 더 빠르다.
v2가 항상 메모리를 덜 쓴다.
평균이 더 좋으므로 무조건 우수하다.
```

대신 workload와 조건을 명시한다.

예:

```text
동일 스레드 64바이트 churn에서는 차이가 측정 변동성 범위였다.

N:N remote-free에서는 v3.4.3의 median throughput이 높았지만
peak RSS도 증가했다.

purge delay를 동일하게 맞추자 기본값 비교에서 관찰된 RSS 차이의
일부가 감소했다.
```

다음 항목을 구분한다.

* allocator algorithm 차이
* upstream 기본 정책 차이
* build option 차이
* THP 차이
* NUMA placement 차이
* benchmark harness overhead
* container 또는 host noise

원인을 직접 측정하지 못했다면 원인으로 단정하지 말고 가설로 표시한다.

---

## 28. 재현성

모든 결과는 다음 조합으로 식별 가능해야 한다.

```text
design revision
source lock hash
container image digest
environment manifest hash
build manifest hash
experiment config hash
benchmark binary hash
random seed
run ID
```

결과 디렉터리 예:

```text
results/raw/<experiment-id>/<run-id>/
```

각 experiment ID는 주요 설정의 canonical representation을 hash해서 생성한다.

동일 experiment ID에서 설정이 달라지는 것을 허용하지 않는다.

---

## 29. 안전 및 자원 사용

benchmark는 높은 CPU와 메모리를 사용할 수 있다.

다음 안전장치를 구현한다.

* 예상 메모리 사용량 사전 계산
* container memory limit 확인
* host available memory 확인
* OOM 가능성 경고
* 최대 실행 시간
* child process timeout
* 종료 signal 처리
* 중간 결과 flush
* interrupted run 표시
* host 설정 원상 복구

운영 장비 또는 사용자 승인 없이 공유 서버에서 전체 benchmark를 실행하지 않는다.

host-wide 설정을 자동으로 영구 변경하지 않는다.

`set_thp.sh`, `set_numa_balancing.sh` 등은 현재 값을 백업하고 복원 방법을 출력해야 한다.

---

## 30. 코드 품질

* C++17 사용
* RAII 사용
* undefined behavior 금지
* raw owning pointer 사용 최소화
* worker exception을 main thread에 전달
* 모든 system call 오류 처리
* config validation 구현
* 구조화된 결과 출력
* timed region에 logging 금지
* benchmark 자체의 동적 할당을 측정 대상과 구분
* 불필요한 production dependency 추가 금지
* deterministic seed 지원
* 종료 시 allocation 정합성 검증
* source file별 역할을 명확히 분리

복잡한 최적화를 추가하기 전에 correctness test를 작성한다.

benchmark harness 변경으로 기존 결과와 호환성이 깨지면 result schema version을 올린다.

---

## 31. 완료 조건

다음 조건을 모두 만족해야 작업이 완료된 것으로 본다.

* v2.1.2와 v3.4.3 source SHA가 고정됨
* v3.5.0 source SHA가 고정되고 fetch/build 상태가 정직하게 기록됨
* 동일 Rocky Linux 8 image에서 세 버전이 빌드됨
* 동일 benchmark binary로 세 allocator가 실행됨
* 실제 로드된 allocator가 검증됨
* CPU와 NUMA affinity가 검증됨
* THP 상태가 기록됨
* local churn scenario가 동작함
* remote-free scenario가 동작함
* queue-only control이 동작함
* correctness test가 통과함
* smoke test가 통과함
* 상세 실험 설계서가 작성됨
* 설계서가 full run 전에 frozen됨
* core cell마다 요구된 valid repetition이 확보됨
* raw data가 보존됨
* invalid run이 문서화됨
* 분석 스크립트가 재실행 가능함
* 그래프와 표가 raw data에서 재생성 가능함
* 상세 실험 보고서가 작성됨
* 미실행 항목과 한계가 명시됨
* README의 재현 명령이 실제로 동작함

---

## 32. 작업 결과 보고 형식

각 작업 종료 시 다음을 간단히 보고한다.

```text
## Completed
- 생성하거나 수정한 파일
- 구현한 기능

## Validation
- 실행한 명령
- 성공한 테스트
- 실패한 테스트

## Experiment status
- design: draft/frozen
- smoke: not-run/pass/fail
- pilot: not-run/pass/fail
- core: not-run/running/complete
- extended: not-run/running/complete
- report: template/partial/complete

## Limitations
- 실행하지 못한 작업
- 권한 부족
- 환경상 통제하지 못한 변수
- 추가 검증이 필요한 사항
```

검증하지 않은 내용을 검증했다고 표현하지 않는다.

---

## 33. 참고할 upstream 자료

구현과 설계 시 다음 upstream 자료를 우선 확인한다.

* `microsoft/mimalloc` tag `v2.1.2`

  * `CMakeLists.txt`
  * `readme.md`
  * public headers
  * runtime option implementation
* `microsoft/mimalloc` tag `v3.4.3`

  * `CMakeLists.txt`
  * `readme.md`
  * public headers
  * runtime option implementation
* `daanx/mimalloc-bench`

  * allocator benchmark scenario
  * remote-free workload
  * Larson-style workload
  * asymmetric allocation/free workload
  * memory allocator benchmark methodology

README 설명과 실제 source 구현이 다르면 해당 tag의 source를 우선한다.

옵션의 존재 여부, 기본값 및 의미를 추측하지 말고 해당 tag에서 직접 검증한다.
