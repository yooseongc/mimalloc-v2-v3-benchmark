# 보안 ON에서 원격 해제와 256 KiB 인계의 비용이 달라진 이유

대상은 v3.7.0 `1ed67b51`과 dev3 `15d1247d`이다. [본 측정](dev3-20261122-report.md)의 원시 자료에 더해, 동일 바이너리로 프로세스 THP 옵션 대조 28회와 syscall 계수 6회를 수행했다. 결과는 본 측정과 별도로 보관했다.

## 4 KiB 원격 해제

두 커밋의 `mi_free_block_mt`는 padding 확인, 보안 수준 4에서 앞쪽 최대 1,024 B 지우기, 다음 포인터 인코딩, 페이지별 xthread_free에 acquire-release CAS로 연결하기, 필요할 때 abandoned page 수집이라는 순서를 공유한다. dev3는 링크 접근을 relaxed atomic으로 명시하고 일부 함수를 정렬하며 local 경로와 빈 페이지 반환 시 검사를 추가한다. 원격 free의 CAS 단계나 zero-on-free 길이를 줄이는 변경은 없다. 보안 모드의 free-list 확장 단위도 달라져 할당 시 만들어지는 접근 패턴은 달라질 수 있다. [원격 해제](../extern/mimalloc-dev3-15d1247d/src/alloc/free.c#L139) · [페이지 확장](../extern/mimalloc-dev3-15d1247d/src/alloc/page.c#L957)

Linux mmap 경로에서 v3.7.0은 `allow_large`와 요청 크기·정렬 조건을 만족할 때 THP advice를 시도한다. dev3는 실제 반환 주소와 길이에 정렬된 큰 페이지가 하나 이상 들어갈 수 있는지 검사한다. 호스트 THP 정책은 madvise였다. 두 버전 모두 프로세스 옵션의 기본값은 2다. [v3.7.0 mmap](../extern/mimalloc-v3.7.0/src/prim/unix/prim.c#L707) · [dev3 mmap](../extern/mimalloc-dev3-15d1247d/src/prim/unix/prim.c#L713) · [주소 검사](../extern/mimalloc-dev3-15d1247d/src/prim/os.c#L189)

보안 ON·내부 large page OFF에서 4 KiB × 32,768개를 원격 해제했다. 같은 네 조건을 매 반복 섞고 7회씩 별도 프로세스로 측정했다. THP는 verify_all 직후 프로세스의 smaps_rollup 측정값이며, 시간은 두 free 구간의 worker wall time이다.

| 빌드 | MIMALLOC_ALLOW_THP | 해제 직전 AnonHugePages (MiB, 매회) | ns/객체 중앙값 [최소, 최대] |
|---|---:|---:|---:|
| v3.7.0 | 0 | 0 | 229.9 [207.1, 305.7] |
| v3.7.0 | 2 | 0 | 220.4 [205.0, 242.7] |
| dev3 | 0 | 0 | 222.6 [213.7, 265.8] |
| dev3 | 2 | 172 | 193.5 [175.8, 245.3] |

THP 허용 시 dev3의 원격 해제 중앙값은 같은 바이너리의 THP 비허용 대비 13.1% 낮았다. 버전 간 차이도 양쪽이 THP를 허용하면 12.2%, 양쪽이 끄면 3.2%였다. 실제 THP 사용 변화는 재현됐고 속도 차이의 방향도 일치한다. 큰 메모리 영역에 흩어진 객체의 앞부분과 padding을 방문하므로 주소 변환 비용 감소가 가능한 설명이다. TLB miss 및 CAS 재시도 횟수는 계측하지 않았고 반복 범위는 겹친다. 이 대조가 지지하는 결론은 THP 정책의 기여이며 기존 측정의 13–20% 전체를 특정 명령이나 TLB 효과에 귀속할 수는 없다. [진단 원시값](../experiments/dev3-20261122-mechanisms-v1/thp.json)

## 256 KiB 인계

내부 large page 0에서는 일반 페이지가 다루는 상한이 약 80 KiB라서 256 KiB는 객체 하나가 페이지 하나를 차지한다. 옵션 1에서는 상한이 512 KiB로 올라가 여러 블록이 하나의 4 MiB 페이지를 공유한다. 보안 ON(수준 4)은 singleton 끝에 guard를 둔다. Linux는 guard를 설치할 때 해당 guard 범위에 release advice와 접근 차단을 적용하고, 반환 시 커밋된 범위의 접근 권한을 복원한다. 다중 블록 페이지에서는 개별 256 KiB 할당과 해제가 매번 이러한 페이지 생성·반환으로 이어지지 않는다. [크기 상한](../extern/mimalloc-dev3-15d1247d/include/mimalloc/config.h#L304) · [guard 선택](../extern/mimalloc-dev3-15d1247d/src/arena/arena-page-alloc.c#L34) · [guard 복원](../extern/mimalloc-dev3-15d1247d/src/arena/arena-page-alloc.c#L790) · [Linux 구현](../extern/mimalloc-dev3-15d1247d/src/prim/unix/prim.c#L882)

같은 dev3 동시 인계 프로그램을 strace -f -c로 실행했다. 표는 프로세스 시작부터 종료까지의 호출 수다. 초기화 비용을 구별하려고 처리량을 1 GiB(4,096개)와 2 GiB(8,192개)로 바꿨다. 시간 비교에는 앞선 비추적 본 측정만 사용한다.

| 보안 / 내부 large page | mprotect (1 → 2 GiB) | madvise (1 → 2 GiB) |
|---|---:|---:|
| ON / 0 | 8,234 → 16,424 | 4,117 → 8,212 |
| ON / 1 | 42 → 40 | 22 → 19 |
| OFF / 0 | 22 → 22 | 5 → 5 |

추가 객체 4,096개당 ON/0에서만 mprotect 8,190회와 madvise 4,095회가 늘었다. singleton의 일반 관리 비용에 보안 guard의 커널 왕복이 객체 단위로 더해진다는 설명과 일치한다. 두 대조군에서는 호출 수가 처리 바이트에 비례하지 않았다. 이 차이는 본 측정의 10.33 대 167.78 GiB/s를 설명하는 강한 근거다. 정확한 시간 기여율은 분해하지 않았다.

RSS는 물리 페이지가 남은 양이다. guard에 대한 madvise의 대상은 guard 범위이며 256 KiB payload 전체를 매번 반환한다는 뜻은 아니다. singleton은 마지막 객체 하나를 해제하면 페이지 전체가 반환 대상이 된다. 다중 블록에서는 같은 페이지의 다른 객체와 재사용·반환 단위를 공유한다. 본 측정 dev3 ON/0은 완료 시 AnonHugePages 0 MiB, ready→done minor fault 19,622–23,447회였다. ON/1은 3회 모두 완료 시 AnonHugePages 176 MiB, minor fault 2–4회였다. major fault는 모두 0이었다. ON/1의 완료 RSS 약 180 MiB 대부분이 실제 THP였고, 1초 뒤에도 남았다. ON/0은 peak 136.9 MiB에서 완료 시 이미 22.7 MiB로 낮아졌다. 실행 시간도 약 41초 대 2.5–3.3초여서 purge 기회와 실제 동시 생존량까지 같았다고 가정할 수 없다. v3.7.0 ON/1은 완료 시 AnonHugePages 0 MiB여도 150.83 GiB/s를 달성했다. 즉 256 KiB 처리량의 큰 도약은 내부 페이지·guard 경로로 설명되고, 두 버전 간 잔류 RSS 차이에는 실제 THP 사용 여부도 반영된다.

[진단 실행기](../observation/diagnose_dev3_20261122.py) · [시스템 호출 계수와 THP 자료](../experiments/dev3-20261122-mechanisms-v1/) · [본 측정의 처리량·RSS](../experiments/dev3-20261122-v1/tables.md)
