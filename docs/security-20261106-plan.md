# dev3 보안 모드 비용 측정

Experiment: security-20261106-v1. Design status: Draft before pilot.
2026-11-06 사용자의 보안 모드 성능 평가 요청에 따라 실행한다.
고정 dev3 d6716d33671c2f621b87be3c7ac016c6ba6b3c94 내부 비교이며 이전 결과와 합치지 않는다.

## 질문과 설정

OFF 대비 MINIMAL / CHECKED / ON / FULL의 처리시간·CPU·메모리 비용은 얼마인가?
CHECKED에 PAC=WEAK만 추가하면 추가 비용이 얼마인가? 보호 수준의 동등성이나
취약점 방어 효과는 평가하지 않는다. MTE 및 하드웨어 PAC는 x86-64에서 미실행.
6 profiles: OFF, MINIMAL, CHECKED, ON, FULL, CHECKED_PAC_WEAK.
MTE=OFF, PAC=OFF(마지막만 WEAK), 다른 옵션은 동일 Release -O3 -DNDEBUG.
각 프로필 별도 build. MI_SECURE 숫자/MI_PAC, verbose 로그로 실제 모드 검증.
ON/FULL의 padding/zero-on-free와 FULL의 guard page로 CPU/RSS 비용 증가 가능성을
가정하되 방향·크기를 사전 확정하지 않는다.

## 환경

동일 Rocky 8 이미지 sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877,
GCC 8.5, x86-64 WSL2. cpuset 0,2,4,6,8,10 / NUMA node0; memory 4 GiB, swap 금지,
quota 없음, network none. THP madvise 유지, 실제 AnonHugePages 수집.
host load/frequency 미통제. 공통 binary + LD_PRELOAD, clean MIMALLOC environment.
이전 동결 코드는 수정하지 않고 활성 observation controller만 재사용한다.

## 측정

1. 새 local_batch.cpp: 한 스레드 CPU2에서 1024개 할당→FIFO 해제 반복,
   크기64/4096 B, first/last write·검증·checksum. warm-up100 batches.
   순수 malloc 호출만의 시간이 아니라 payload 접근/검사/free도 포함한다.
2. 활성 concurrent.cpp: 크기64/4096 B, 2 producer-consumer 쌍, 128 MiB 생존 상한,
   256객체 인계·full write·검증. CPU0/2/4/6, controller8, observer10.
   1번과 touch/topology가 다르므로 두 시나리오 절대 비용을 직접 빼지 않는다.
3. 활성 lifecycle.cpp: 4KiB×32768=128MiB 할당/쓰기/동일 스레드 해제/idle1초/재할당.
   6모드×3회=18, phase 시간과 정확 RSS. 추가 forced-collect는 범위 밖.

1/2는 각 크기×6모드×5회=60씩. 총 본 측정138회.
smoke: local/concurrent 각12 및 lifecycle6=30. pilot local/concurrent 각12=24.
local pilot10000 batches, concurrent pilot1GiB. 조건별 가장 빠른 pilot 속도×3초와
가장 느린 속도×12초 중 작은 작업량을 사용한다. local 최소1000 batches,
concurrent 최소1GiB, 512객체 배수. 모든 모드에서 같은 작업량으로 동결한다.
실제 시간 목표 미달은 제외 사유가 아니며 보고한다. seed2026110602로 각 반복 내
6모드 순서를 무작위화. fresh process, 순차 실행. 예상 15–30분.

## 동결·판정·분석

build/모드검증→smoke→pilot→plan.json 동결→measured.
소스/라이브러리/실행파일/controller/artifact/pilot hash를 고정한다.
버전/로드경로/hash, checksum/개수, CPU affinity, final live0, swap/throttling,
timeout/crash 검증 실패 시 raw 보존 후 중단한다. 속도에 따른 제외는 하지 않는다.
중앙값·최소/최대, 같은 반복의 profile/OFF elapsed 비율, CPU·RSS 및
CHECKED_PAC_WEAK/CHECKED 비율을 별도로 보고한다. 반복5회 탐색 관찰이며
작은 차이의 유의성/동등성이나 보안상 안전성을 입증하지 않는다.
raw/results/security-20261106-v1, 계약/experiments/security-20261106-v1,
보고서/docs/security-20261106-report.md. 재현 runner는 observation/security_20261106.py.
