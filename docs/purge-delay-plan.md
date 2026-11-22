# 반환 대기시간을 맞췄을 때의 RSS 비교

Date: 2026-10-24. Design status: Frozen before execution.
Experiment: purge-delay-v1. plan.json에 문서·실행기·소스·artifact hash와 동결 시각을 기록한다.

질문: 네 버전의 purge 대기시간을 같게 하면 RSS 패턴이 비슷해지는가?
앞서 차이가 컸던 1 KiB, 할당자/해제자 2쌍(4 worker), 인계 공간 상한 128 MiB만 본다.
A가 할당·전체 쓰기·인계하고 B가 확인·해제하는 흐름이다. 실제 생존량은 상한과 다르다.
같은 객체 수 193,755,136개를 처리한 뒤 worker를 살려 두고 5초 idle한다.

소스에서 기본 purge_delay는 v2.1.2=10 ms, v3.5.0/v3.5.3/v3.6.0=1000 ms다.
arena_purge_mult 기본값도 v2=10, v3=4로 다르다. 이번 주 비교에서는
**purge_delay=10 또는 1000 ms, arena_purge_mult=1**로 네 버전을 맞춘다.
이는 두 옵션으로 반환 대기시간을 정렬한 비교이며 purge_delay 단독 변경의 효과로
해석하지 않는다. 배수가 같아져도 버전별 page/segment/arena 구조·purge 실행 조건,
THP 최소 반환 단위·page 회수 정책까지 동일해지는 것은 아니다.

네 버전 × 두 시간 × 세 fresh process = 24회. 각 반복 블록에서 8개 조건을
seed 2026102402로 섞는다. 비교 중 다운로드·소스 변경·라이브러리 재빌드는 하지 않는다.
release-v360-v1의 검증된 라이브러리를 SHA로 확인해 사용한다.
이미 실행한 데이터를 새 반복 표본으로 합치지 않는다.

준비 단계에 실제 purge_delay, arena_purge_mult, purge_decommits getter를 출력한다.
버전별 헤더로 enum 값만 추출한 뒤, 네 버전에 공통인 진단 실행파일 하나를 만든다.
현재 observation/concurrent.cpp의 timed workload는 변경하지 않는다.
현재 run_concurrent.py를 별도 파생 파일로 만들어 환경변수와 getter 검증만 추가한다.
준비 시 설정 안 한 기본값도 짧은 실행으로 실제 확인한다.

검증: 기본값 확인 4회 + 정렬한 옵션의 payload 전체 검증 smoke 8회.
본 실행은 객체 앞뒤 identity·checksum·할당/해제 개수·최종 생존량 0,
allocator 버전/경로/maps·library/binary SHA·worker CPU 배치·swap·throttling을 확인한다.
실패나 timeout 기록을 남기고 중단하며, 삭제·제외 후 재시도하지 않는다.

측정: 약 100 ms RSS 샘플, 초기 적재 완료/작업 완료/idle 0.1·1·5초의 정확한 RSS,
AnonHugePages, PSS, 작업 중 생존량, 처리 시간·worker CPU·page faults.
그림은 작업 구간의 경과시간과 완료 이후 실제 관측 시각을 구분한다.
idle 중 allocator 호출이나 강제 collect를 추가하지 않는다. idle만으로 예약 purge가
백그라운드에서 반드시 수행된다고 가정하지 않는다.

환경: 기존 고정 Rocky Linux 8.9 image, CPU 0,2,4,6,8,10, NUMA node 0,
network none, 동일 CPU/메모리 한도. host 부하·주파수·가상화는 미통제다.
예상 시간 5~8분, payload 상한 128 MiB. 다른 객체 크기·same-thread 흐름은 이번 범위 밖이다.
각 3회 중앙값과 전체 범위를 보고하며 통계적 동등성 검정이나 보편적 성능 결론을 내리지 않는다.
다른 옵션의 기본값 차이는 유지되므로 이 실험을 완전한 동일 정책 비교라고 부르지 않는다.
