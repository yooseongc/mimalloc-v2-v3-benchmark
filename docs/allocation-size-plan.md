# 할당 크기를 키웠을 때의 처리 흐름

2026-10-24. Experiment: allocation-size-v1. Design status: specified before pilot;
pilot의 속도로 공통 작업량을 정한 뒤 plan.json에 hash와 동결 시각을 저장한다.

질문: 4 KiB 객체를 16/64/256 KiB로 키우면 바이트 처리량이 좋아지는가?
객체/s와 완료 payload GiB/s를 함께 보고 객체가 커져 단순히 객체 수가 줄어드는
효과와 구분한다. 전체 쓰기·인계·검증·원격 해제가 포함된 흐름을 측정한다.
순수 allocator 호출 비용이나 실제 응용의 성능 향상으로 해석하지 않는다.

네 버전 v2.1.2/v3.5.0/v3.5.3/v3.6.0을 유지한다. purge-delay-v1에서 검증한
소스 SHA와 라이브러리를 재사용하되 새 바이너리와 결과 namespace를 사용한다.
purge_delay=1000 ms, arena_purge_mult=1로 통일한다. 다른 정책은 각 버전 기본값이며
THP 최소 반환 단위 차이는 유지된다. 완전한 동일 정책 비교라고 부르지 않는다.

A 할당·전체 쓰기, B 앞뒤 identity 확인·해제, 독립 2쌍(4 worker), 요청 생존량
상한 128 MiB를 유지한다. 시작 시 128 MiB를 미리 적재한다.
기존 활성 concurrent.cpp의 batch를 객체 수 256개 고정에서 **payload 256 KiB 고정**으로
바꾼 별도 파생 소스를 생성한다. batch당 객체 수는 64/16/4/1개가 된다.
따라서 크기를 키워도 인계 1회의 바이트량과 인계 슬롯 수는 변하지 않는다.
이전 바이너리 결과를 새 비교 표본으로 합치지 않으며 4 KiB도 다시 측정한다.

모든 크기·버전에서 완료 payload 총 바이트 수를 같게 한다.
각 16조건 pilot 1회에서 8 GiB를 처리한 후 가장 빠른 바이트 처리량 × 3.5초를
128 MiB 배수로 올림해 전체 조건 공통 작업량으로 고정한다(최소 8 GiB).
이는 같은 데이터 양을 더 큰 객체로 묶어 처리할 때의 차이를 보는 설계다.
timed 구간에서 새로 쓰는 양은 총 완료 payload에서 처음 적재한 128 MiB를 뺀 값이다.

smoke: 16조건, 128 MiB 상한, 총 256 MiB, 전체 payload 검증.
measured: 4크기 × 4버전 × 3회 = 48회. seed 2026102403으로 반복 블록의 16조건을
무작위화한다. fresh process를 사용하고 마지막 해제 후 worker를 살린 채 idle 1초를
관찰한다. 이 실험의 초점은 작업 중 처리량·RSS이며 이전 idle 5초 값과 합치지 않는다.

검증: 버전·라이브러리/공통 실행파일 SHA·maps, 실제 delay/배수 getter,
객체 개수·checksum·최종 생존량 0, worker CPU 배치, swap·throttling.
실패는 보존하고 중단한다. 소급 제외나 결과에 따른 작업량 변경은 하지 않는다.
약 100 ms RSS·생존량 샘플, 준비/완료/idle 시점의 정밀 RSS·THP·fault,
전체 시간과 worker CPU를 기록한다. 최종값은 3회 중앙값·최소/최대다.

환경: 동일 고정 Rocky Linux 이미지 sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877,
CPU 0/2/4/6 worker, 8 제어, 10 관측; cpuset 0,2,4,6,8,10, NUMA node 0,
network none. host 주파수·부하 및 WSL2 가상화는 미통제다.
메모리 쓰기 대역폭·queue 동기화·실제 생존량의 변화가 포함되므로 크기별 차이를
allocator 알고리즘 하나에 귀속하지 않는다. 예상 실행 시간 6–12분.
