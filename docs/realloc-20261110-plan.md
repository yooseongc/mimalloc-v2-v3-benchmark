# realloc 축소 변경 직접 측정

Experiment: realloc-20261110-v1. Design status: Draft before smoke/pilot.

사용자 승인: 2026-11-10 realloc 설명 및 변경 전후 비용/RSS 직접 측정.
기존 동결 소스/실행기/결과는 수정하거나 합치지 않는다.

## 고정 비교와 질문

- before: 90d604b8d53ade9873387db5295304893816144e
- strict: b28854bfea271b531c8d0da52acd72194845117b (12.5% 기준)
- tail: 1af6580b14dc9f7604d6a417a058ca0ef803b29c (huge tail reset)
- upstream https://github.com/microsoft/mimalloc; 모두 원본 소스 별도 checkout/build.

인접 커밋으로 축소 기준과 tail reset을 분리한다. same-heap 수정은 세 대상에
모두 들어 있으므로 이 실험의 독립 변수가 아니다. moving dev3 HEAD를 쓰지 않는다.
가설: 25% 축소에서 strict는 복사 비용을 늘리고 usable 용량을 줄인다. huge의 tail은
포인터/usable 용량을 유지하며 reset 비용을 내고 RSS를 줄일 수 있다. 실제 방향/크기는 측정한다.

## 환경

Rocky8 image sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877.
동일 GCC Release -O3 -DNDEBUG, MI_SECURE/MTE/PAC OFF, 동일 executable + LD_PRELOAD.
cpuset 0,2 / node0, worker CPU0, controller CPU2; 4GiB, swap 금지, quota 없음,
측정 network none. THP/host 전역 설정 유지. WSL2 부하/주파수와 기존 상주 컨테이너 미통제.
전체 runtime MIMALLOC 변수 제거(upstream-default). NUMA는 cpuset-mems만 설정.

## 작은 질문 중심 프로그램

2 APIs: malloc/realloc/free 및 mi_malloc_aligned/mi_realloc_aligned/free (64B).
2 sizes: 4KiB, 8MiB. 각 블록 usable size 기준 새 크기 15/16, 3/4, 1/4.
한 배치 요청량 128MiB, 모든 요청 바이트 memset 후 축소. 각 실행 fresh process.
준비/쓰기/검증은 timed region 밖. 배치 전체 realloc loop(포인터 배열 대입 포함)의
wall/CPU, faults 측정. 이동 개수는 저장한 uintptr_t 주소로 timed region 밖에서 검사.
단일 tiny realloc latency로 오해하지 않도록 ns/call은 batch aggregate임을 표시한다.

RSS 단계: baseline, 전체 할당/쓰기, 축소 직후, idle 1초, 강제 mi_collect(true),
전체 해제/강제 회수. smaps_rollup Rss/Pss/AnonHugePages/Swap와 VmHWM 수집.
Linux reset은 MADV_FREE일 수 있어 LazyFree도 수집한다. 회수 가능해도 RSS에 남을 수 있다.
축소 직후 checkpoint는 보존 영역 검증 직후이며 검증은 retained prefix만 읽는다.
idle과 강제 회수는 비용 측정에서 제외. forced collect는 정상 동작과 별도 표시.
payload 첫/끝 및 매 OS 페이지 검사; smoke는 전체 보존 바이트 검사.
retained prefix 보존, 정렬, allocation/free 개수, 최종 live0 검증.

비용 반복은 별도 프로세스에서 warmup 1배치 후 동일 준비→축소→검증→해제를 반복한다.
pilot 4배치로 총 loop 경과시간을 구하고 조건별 가장 빠른 버전 기준 1초 목표,
최소4/최대64배치로 동결한다. setup/touch는 별도 elapsed에만 들어가며 realloc 시간 합과
혼동하지 않는다. fast path 자체의 누적 시간이 짧을 수 있으므로 작은 차이를 단정하지 않는다.

## 순서, 동결, 판정

build→전체36조건 smoke→전체36조건 pilot→plan.json hash 동결→measured.
각 조건 5회, 반복 내 버전 순서 seed20261110 무작위화. 각 실행 순차 실행.
본 측정 180 RSS + 180 cost fresh processes. 예상 8–20분, 생존 요청량128MiB.
소스/실행기/라이브러리/binary/초기 계획/smoke/pilot hash를 동결한다.
allocator 경로/hash/version, affinity, swap, throttling, OOM, timeout/crash, 내용 검증
실패는 raw 보존 후 중단한다. 속도 기준 제외 없음. 실패 수정은 amendment 기록.
median/min/max 및 같은 rep의 strict/before, tail/before, tail/strict 비용 비율을 보고한다.
5회 탐색 관찰로 서비스 전체 처리량/유의성/방어 효과를 주장하지 않는다.
RSS checkpoint는 정확한 단계 값이고 transient peak는 VmHWM(커널 accounting)이다.

재현: observation/realloc_20261110/run.ps1. 결과 results/realloc-20261110-v1,
manifest/summary experiments/realloc-20261110-v1, 보고 docs/realloc-20261110-report.md.

## Pre-freeze amendment

2026-11-10: 최초 smoke 프로세스는 LazyFree 수집 추가 전 실행기를 로드했다.
기존 smoke/pilot은 보존하고 preflight 3조건(8MiB→75%, 세 버전)에서 새 수집을 검증한다.
본 측정은 모두 LazyFree와 종료 affinity/OOM counter 검증을 포함한다. workload와
제외 기준 및 반복 수는 바꾸지 않는다. frozen 상태/시각/해시는 plan.json을 따른다.
