# mimalloc v3.7.0 비교 계획

2026-11-18. Experiment: release-v370-v1. Design status: Draft before pilot.
사용자가 계획·구현·검증·측정·보고서 작성을 승인했다. 기존 동결 자료는 보존한다.

## 질문과 가설

v3.6.1 대비 v3.7.0의 처리 비용, RSS 보유/반환, 원격 해제 통계 귀속을 확인한다.
릴리스의 purge 수정과 realloc 절약 설명은 가설의 배경이며 성능 개선을 전제하지 않는다.
기본 비교는 MI_SECURE=OFF이며 하드웨어 MTE/PAC와 방어 효과는 범위 밖이다.
realloc 자체와 thread churn은 기존 별도 진단으로 보존하며 이 릴리스 기본 matrix와 합치지 않는다.
소스 사전 점검은 docs/v370-source-notes.md에 기록한다.

## 소스와 환경

v2.1.2=43ce4bd7fd34bcc730c1c7471c99995597415488,
v3.5.0=18b08671c9302247bfb682286e6bf3cc1773f801,
v3.5.3=d4881d338125e1cb7c47ba4cfb398d6f7c0c8d45,
v3.6.0=b18ab4eef383f655e760881b02eff8af02800879,
v3.6.1=56dc5eb80145f9a3ba7ca23d47c6a248b9d8586c.
v3.7.0=1ed67b5156a763441d2ec3c20221a7b3cd866129.
v3.7.0 annotated tag object=7d589caad1c331b677719adb3c8f082c15400f3d.

고정 Rocky Linux 이미지 sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877.
여섯 버전을 동일 GCC Release -O3 -DNDEBUG, MI_SECURE=OFF로 새로 빌드한다.
소스 수정 없이 기존 활성 observation 프로그램을 사용한다. 폐기된 하네스는 사용하지 않는다.
cpuset 0,2,4,6,8,10, NUMA node 0, network none. worker 0/2/4/6,
controller 8, observer 10. lifecycle은 worker 0/2, controller 4, observer 6.
현재 topology와 메모리 가용량을 확인하며 host THP 설정을 바꾸지 않는다.
컨테이너 메모리 상한은 6 GiB, swap은 금지하고 CPU quota는 두지 않는다.
빌드 명령·캐시·소스/바이너리/library hash·실제 로드 경로·환경을 보존한다.

## 실행 범위

1. 기본 lifecycle: 4 KiB × 32768개, 128 MiB; 동일/다른 스레드 해제,
   할당·쓰기·절반 해제·전체 해제·5초 idle·재사용. 6버전 × 2조건 × 3회=36회.
   별도 강제 collect 진단은 각 1회=12회.
2. 기본 동시 처리: 64 B/1 KiB/4 KiB, 128 MiB 상한, 1/2쌍과
   4 KiB/512 MiB/2쌍. 7조건 × 6버전 × 3회=126회.
   smoke 전체 payload 검증 후 42개 pilot에서 조건별 가장 빠른 속도 × 3.5초를
   512객체 배수로 고정한다. 최소 1 GiB payload. 버전별 동일 작업량.
3. stats: v3.5.3/v3.6.0/v3.6.1/v3.7.0, 64 B/4 KiB, 자동 병합 on/off,
   각 2회=32회. 명시적 API 진단이며 LD_PRELOAD 성능과 분리한다.
4. purge: purge-delay-v370-v1. 1 KiB, 2쌍, 128 MiB, delay 10/1000 ms,
   arena_purge_mult=1. 새 기본 pilot에서 정한 작업량을 사용한다.
   기본값 getter 6회, smoke 12회, 본 측정 36회. idle 5초.
5. 크기: allocation-size-v370-v1. 4/16/64/256 KiB, 2쌍, 128 MiB,
   256 KiB 인계 배치, delay1000/mult1. smoke/pilot 각24회, 본 측정72회.
   모든 조건 동일 총 바이트: pilot 최대 속도 ×3.5초를 128 MiB 배수로 올림,
   최소 8 GiB. idle 1초.

기본 비교는 다른 런타임 옵션을 설정하지 않는다. purge/크기 비교는 두 옵션만
정렬하며 완전한 동일 정책 비교라고 부르지 않는다. 준비 적재와 warm-up은 기존
활성 프로그램대로 유지한다. 전체 쓰기·인계·검증이 포함된 비용이며 순수 malloc 비용이 아니다.
버전 순서는 반복 블록 안에서 seed 20261118/2026111802/2026111803으로 섞는다.
모든 실행은 fresh process. 측정은 동시에 돌리지 않는다. 예상 총 30–55분.

## 동결과 판정

smoke → pilot → stats → freeze → measured. purge는 기본 pilot 작업량을 사용하므로
별도 pilot 없이 prepare에서 동결하고 smoke 후 측정한다. 크기 비교는 별도 pilot 후 동결.
plan.json에 동결 시각과 문서·실행기·소스·artifact 및 pilot hash를 기록한다.
측정 중 수정하지 않고 실패 기록을 보존하며 중단한다. 기존 valid 결과만 설정 확인 후 재개한다.
버전/경로/hash, payload/checksum/개수, 최종 생존량 0, affinity, swap/throttling,
timeout을 검증한다. 과거 결과와 새 반복을 합치지 않는다.

중앙값과 최소/최대, 처리량·worker CPU·RSS·생존량·THP·fault를 보고한다.
3회는 탐색용이며 작은 차이의 통계적 유의성/동등성, p99, 실제 응용 우열을 주장하지 않는다.
WSL2 가상화, host 부하·주파수는 미통제다. RSS 잔류는 누수 증거가 아니며
idle만으로 purge가 반드시 수행된다고 가정하지 않는다. 원인 추정은 관찰과 구분한다.

재현은 observation/RELEASE_V370.md를 따른다.

