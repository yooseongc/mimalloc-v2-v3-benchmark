# mimalloc v3.6.0 처리 비용과 메모리 흐름 비교

작성일: 2026-10-24. Design status: Frozen (pilot 완료, 작업량은 plan.json에 기록).

질문은 동일한 작업의 처리 비용·메모리 보유/반환 패턴이 v3.6.0에서 어떻게 달라졌는지,
그리고 v3.5.3에서 확인한 A 할당/B 해제 통계 귀속 방식이 바뀌었는지다.
v2.1.2, v3.5.0, v3.5.3을 모두 유지한다. 과거 수치를 새 수치와 직접 비교하지 않고
네 버전을 현재 환경에서 같은 순서 블록 안에 섞어 다시 실행한다.

v3.6.0 annotated tag object는 `79cf666d6a78c3ed59dc9b77e171a29425aec6ba`,
실제 commit은 `b18ab4eef383f655e760881b02eff8af02800879`이다.
나머지 버전은 memory-behavior-v1의 고정 source SHA를 유지한다.

## 범위와 예상

- 기존 질문 중심의 `observation/lifecycle.cpp`와 `concurrent.cpp`를 그대로 사용한다.
  폐기된 benchmark 하네스는 사용하지 않는다. 새 실행기와 빌드/원자료 namespace는
  `release-v360-v1`이며 기존 동결 자료를 덮어쓰지 않는다.
- 네 버전을 같은 Rocky Linux 이미지와 GCC Release -O3 -DNDEBUG로 새로 빌드한다.
  지원하는 공통 빌드 선택만 지정하고 나머지는 upstream 기본값을 유지한다.
  프로파일러를 runtime에서 활성화하지 않는다. build flags, source/library SHA,
  환경, 실제 로드 경로·버전을 기록한다.
- 단계별 흐름: 4 KiB × 32,768개(128 MiB), 같은 스레드/다른 스레드 해제,
  할당·쓰기·50% 해제·나머지 해제·5초 idle·재할당·재쓰기. 각 3회, 총 24회.
  OS 반환 여부를 확인하는 별도 A collect(true) 실행은 조건당 1회, 총 8회.
  기존 30초 대신 첫 관찰을 5초로 제한하며 그 이후 반환 시점을 추정하지 않는다.
- 동시 처리: 64 B·1 KiB·4 KiB, 공간 상한 128 MiB, 1/2쌍;
  4 KiB·512 MiB·2쌍을 추가한다. 7조건 × 4버전 × 3회 = 84회.
  할당·전체 쓰기·인계·앞뒤 내용 검증·free를 포함한 흐름이며 순수 malloc 비용이 아니다.
  공간 상한과 실제 관측 생존량을 구분한다.
- smoke에서 전체 payload, 객체 수/체크섬, CPU 배치, 로드 경로, 생존량을 검증한다.
  pilot은 4개 크기/쌍 조합이 아닌 위 7조건 모두에서 각 버전 1회 실행한다.
  각 조건의 가장 빠른 pilot으로 약 3.5초 분량을 계산하고 512개 배수로 고정한다.
  각 버전에 같은 작업량을 사용한다. 속도 우열을 확인한 뒤 작업량을 바꾸지 않는다.
- stats: v3.5.3과 v3.6.0만 A 할당/B 해제, 64 B/4 KiB 1,000개,
  두 스레드 생존, 자동 통계 병합 on/off, 각 2회. 버전별 헤더로 별도 빌드하고
  같은 단계·getter를 사용한다. total-current는 free 호출 수가 아닌 파생 해제 bytes다.
  v3.6.0에서는 collect_merges_stats가 stats_merge_on_collect로 이름이 바뀌었고
  stats_merge_threshold(기본 512 KiB) 자동 병합이 추가되었다. 통계 보존 진단에서는
  두 자동 병합을 모두 끈다. 기본값 진단에서는 두 기본값을 유지한다. 실제 getter로 확인한다.

## 관찰과 판정

기존 코드에서 검증한 CPU 배치 0/2, 4/6, controller 8, observer 10을 동시 처리에
사용한다. 단계 흐름은 A0/B2/controller4/observer6이다. 컨테이너 cpuset은
0,2,4,6,8,10, NUMA node 0, network none, memory/quota 무제한으로 동일하다.
현재 WSL2 가상화·host 부하·주파수는 통제하지 못하는 한계로 기록한다.

버전 순서는 seed 20261024로 각 반복 블록에서 섞는다. 모든 실행은 fresh process다.
RSS, idle RSS, THP, page faults, 단계별 시간, 처리량, worker CPU, 실제 생존량을
기록하고 중앙값과 최소/최대 범위를 함께 본다. 각 3회는 탐색용이며 통계적 동등성,
실제 응용에서의 보편적 우열, p99를 판정하지 않는다. RSS 잔류를 누수로 해석하지 않는다.

버전/경로/SHA 불일치, payload/체크섬/개수 불일치, affinity 위반, timeout, swap,
CPU throttle은 실패 기록을 보존하고 중단한다. 원자료를 삭제해 재실행하지 않는다.
측정 중 다운로드하지 않는다. 예상 총 시간 15~25분, payload 상한 512 MiB,
공간 상한은 프로세스 RSS 한도가 아니며 실제 사용량도 관찰한다.

v3.6.0의 기본 page_reclaim_on_free 변경, cache-line 배치 및 통계 코드 변경은
소스에서 확인한다. 관찰과 소스상 가능한 원인을 구분하며 필요하면 단일 변수
진단을 별도 namespace로 추가한다. 기본값 비교를 동일 정책 비교라고 부르지 않는다.

## 재현

`observation/release_v360.py`를 고정 이미지
`sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877`에서
build → smoke → pilot → freeze → measured → stats 순서로 실행한다.
실제 동결 시각과 이 문서·runner·source·artifact hash는 plan.json에 저장한다.
