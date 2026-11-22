# v3.7.0 내부 large page 정책 A/B

2026-11-18 사용자 승인: “Large page 켜고해봐요”.
Namespace: `v370-large-pages-v1`. 실행 전 설계이며 동결 계약은 해당 plan.json이다.

목적은 MI_ENABLE_LARGE_PAGES=1이 256 KiB 저하를 회복하는지 확인하는 것이다.
OS large pages/THP 설정은 변경하지 않는다. upstream 소스도 수정하지 않는다.
v3.6.1 기본, v3.7.0 기본, v3.7.0 CMAKE_C_FLAGS=-DMI_ENABLE_LARGE_PAGES=1을
각각 별도 디렉터리에 새로 빌드한다. 나머지 CMake 인수는 기존 release-v370-v1과 같다.
공통 실행 파일은 동결 allocation-size-v370-v1 바이너리를 해시 검증 후 복사한다.

4/16/64/256 KiB, producer/consumer 2쌍, 생존량 상한128 MiB, 인계 배치256 KiB,
전체 쓰기, purge_delay1000/arena_purge_mult1. 기존 총 처리량732.625 GiB 이상으로
모든 셀의 처리 바이트를 동일하게 한다. smoke 12회(전체 검증), pilot 12회 이후
가장 빠른 pilot 기준3.5초에 해당하는 처리량과 기존 처리량 중 큰 값을128 MiB 단위로
올림하고 동결한다. 측정은3개 반복 블록마다12셀 무작위화(seed2026111804), 총36회.
중앙값과 최소–최대를 보고하고 유의성 또는 다른 workload로의 일반화를 주장하지 않는다.

기존 고정 Rocky8 이미지, cpuset0,2,4,6,8,10, mems0, memory/swap6GiB,
네트워크 차단, quota 없음. controller CPU10, worker0/2/4/6, coordinator8.
환경·source/build/library/binary/runner 해시, 페이지 배치와 실제 컴파일 매크로를 기록한다.
allocator 정체, 개수/checksum, CPU 배치, live=0, swap=0, throttling 없음 검증 실패 시
중단하고 원본을 보존한다. 사후 성능값으로 제외하지 않는다. 예상 전체10분 이내.

처리량, 작업 중 RSS/생존량, minor fault, producer/consumer CPU를 보고한다.
GiB/s는 완료 payload이며 DRAM 대역폭이 아니다. CPU는 대기/쓰기 등을 포함한다.
이 매크로는 여러 파생 정책을 함께 바꾸므로 그 정책 묶음의 효과로 해석한다.
기존 동결 실험 파일과 결과는 변경하거나 새로운 측정과 합치지 않는다.
