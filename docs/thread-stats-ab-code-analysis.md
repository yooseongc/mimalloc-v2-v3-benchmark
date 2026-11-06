# v3.5.3 A 할당 / B 해제: 통계 귀속 차이의 코드 원인

분석·검증 완료: 2026-09-22. 대상 commit:
`d4881d338125e1cb7c47ba4cfb398d6f7c0c8d45`.

**원인은 페이지 단위 통계 정산과 full-page abandonment의 조합이다.**
free 호출자의 실적을 바로 증가시키지 않고, 페이지의 사용량 감소를 나중에 정산한다.
정산을 수행하는 경로가 선택한 theap에 감소분이 반영된다. 따라서 원래 할당자 A와
실제 해제자 B 중 어느 쪽에 잡힐지는 그 페이지의 소유 상태에 따라 달라진다.

## 1. free 호출마다 B의 통계를 증가시키지 않는다

[`src/free.c:63`](../extern/mimalloc-v3.5.3/src/free.c)의
`mi_free_block_mt`는 원격 free를 `page->xthread_free`에 CAS로 연결한다.
기존에 소유자가 있으면 여기에서 B의 `malloc_normal`을 감소시키지 않는다.
소유권 없는 abandoned 페이지를 새로 획득한 경우에만
`mi_free_try_collect_mt`로 들어가 그 스레드에서 추가 처리를 한다.

[`src/page.c:241`](../extern/mimalloc-v3.5.3/src/page.c)의
`mi_theap_page_update_stats`는 다음 식으로 마지막 정산 이후 해제량을 복원한다.

```c
free_count = last_used + alloc_count - used;
```

같은 파일의 `mi_theap_page_merge_stats`(185–218행)는 그 수에 객체 크기를
곱한 bytes를 **전달받은 theap의** `malloc_normal.current`에서 뺀다.
이 계산에는 “각 free를 호출한 스레드”의 별도 기록이 없다.

이는 코드 주석으로도 확인되는 설계다.
[`include/mimalloc/types.h:417`](../extern/mimalloc-v3.5.3/include/mimalloc/types.h)는
할당 수와 사용량을 압축해 빠른 경로의 코드를 단순하게 하고, slow path에서 통계를
갱신하기 위한 구조라고 설명한다. 이 목적은 소스로 확인되지만, 이번 검증이 실제
성능 향상 폭까지 측정한 것은 아니다.

## 2. 어느 theap을 선택하는가

`src/page.c:150`의 `mi_theap_of_page`는 페이지의 thread ID가 현재 스레드와
같으면 `page->theap`을 쓰고, 다르면 `_mi_page_associated_theap_peek(page)`를 쓴다.

[`include/mimalloc/prim-tls.h:424`](../extern/mimalloc-v3.5.3/include/mimalloc/prim-tls.h)의
후자는 `page`의 공유 heap에 연결된 **현재 스레드의 TLS theap**을 조회한다.
원래 할당자의 theap을 찾아가는 함수가 아니다. 이번 시험은 A와 B가 같은 공유 heap에
각자의 theap을 연결했으므로, B에서 이 경로를 밟으면 B의 통계가 선택된다.
해당 theap이 없으면 상위 heap 통계로 반영될 수도 있어 시험 조건이 중요하다.

- A가 계속 소유한 페이지: B는 remote-free 목록에 연결한다. A collect가 이를
  수집하고 사용량·통계를 갱신하므로 해제량이 A에 잡힌다
  (`src/theap.c:97–103`).
- A가 소유권을 놓은 페이지: B free가 임시 소유권을 얻어 수집·반환하거나 자신의
  theap으로 회수할 수 있다 (`src/free.c:520–554`). 페이지 반환 시에도
  `_mi_page_update_stats`를 호출한다 (`src/arena.c:1300–1314`). B가 처리하는
  이 정산 경로에서는 해당 공유 heap의 B theap에 감소분이 잡힌다.

`src/arena.c:1331–1334`에는 abandonment 시 미리 통계를 갱신하지 않으면
나중에 다른 스레드가 회수하면서 그 스레드에 할당·해제가 귀속될 수 있다는 주석까지 있다.
이번에는 할당분은 A에서 정산되고, 그 이후 B가 해제한 감소분의 귀속이 갈린다.

## 3. 왜 정확히 40개 / 960개인가

[`src/options.c:167`](../extern/mimalloc-v3.5.3/src/options.c)의
`page_full_retain` 기본값은 **2**다. `src/theap.c:196–197`에서 theap에 적용한다.
`src/page.c:949–976`의 페이지 검색은 보유 한도를 초과한 full page를
`mi_page_to_full`로 보낸다. abandonment가 허용되어 있으면 이는
`_mi_page_abandon`으로 이어진다 (`src/page.c:554–562`).

이 빌드에서 4 KiB 객체는 64 KiB small page의 메타데이터·정렬 여백 뒤에
**15개**씩 들어간다. 이는 앞서 공식 heap visitor로 읽은
[영역 정보](../experiments/memory-behavior-v1/layout-v353.json)에서도 확인했다.

```text
1,000개 = 꽉 찬 66페이지 × 15개 + 마지막 페이지의 10개
A에 남음 = 보유하는 2페이지 × 15개 + 마지막 10개 = 40개
abandoned = (66 − 2)페이지 × 15개 = 960개
```

따라서 A의 해제 감소분은 `40 × 4096 = 163,840 B`, B는
`960 × 4096 = 3,932,160 B`가 된다. 원래 결과와 정확히 일치한다.

64 B × 1,000은 하나의 small page에 들어가 이 full-page abandonment가
발생하지 않는다. B가 모두 free해도 A가 소유한 페이지의 remote-free 목록을
A가 정산하므로 **1,000개분 전체가 A에 잡힌다.**

## 4. 설정 하나만 바꾼 인과 검증

기존 upstream 라이브러리와 A/B workload를 유지하고 `page_full_retain`만 변경했다.
원본 probe는 보존했다. 새 실행기가 생성한 probe에는 실제 option getter 출력만
추가했다. 자동 병합은 꺼 두고, purge delay는 모두 1,000 ms로 동일하다.
표의 예측은 [설계 기록](../experiments/thread-stats-ab-retention-v353/design.md)에
실행 전에 고정했으며, 두 스레드가 collect를 마치고 병합하기 전 값을 검증했다.

| page_full_retain | 4 KiB A / B 해제량의 객체 수 환산 | 64 B A / B |
|---:|---:|---:|
| -1: abandonment 비활성화 | 1,000 / 0 | 1,000 / 0 |
| 0 | 10 / 990 | 1,000 / 0 |
| 1 | 25 / 975 | 1,000 / 0 |
| 2: 기본값 | 40 / 960 | 1,000 / 0 |
| 4 | 70 / 930 | 1,000 / 0 |

**10개 fresh process 모두 예측과 정확히 일치했다.** 객체 내용, A free=0,
B malloc=0, A malloc=B free=1,000, 전체 누적 할당 bytes/count, 최종 current=0,
최종 parent 병합값도 검증했다. 실패한 실행은 없다.
이 검증은 결정적 통계 귀속 확인이며, 성능 pilot/core/extended 측정은 해당하지 않는다.

[실행기](../observation/check_stats_ab_retention.py) ·
[전체 결과·SHA·빌드 명령](../experiments/thread-stats-ab-retention-v353/results.json).

```powershell
docker run --rm --pull=never --network none --mount 'type=bind,source=C:\Users\user\workspace\mimalloc-test,target=/work' --workdir /work sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877 python3 observation/check_stats_ab_retention.py
```

## 판단

현재 결과의 40/960 분리는 우연이나 계측 노이즈가 아니라 페이지 보유 정책에 따른
재현 가능한 통계 귀속이다. 추가 collect 후에도 분배는 그대로다. OS에 물리 메모리를
언제 돌려주는지와 별개로, 감소분을 어느 통계에 적는지의 문제다.

이 구현의 thread 통계를 스레드별 malloc/free 호출 실적으로 읽는 것은 부정확하다.
4 KiB 최종 A current=+3,932,160 B / B current=−3,932,160 B도 이 비대칭 회계로
설명된다. 전체 합계는 0이며 개별 current가 각 스레드의 실제 생존 객체 bytes를
뜻하지 않는다. 이 시험은 통계 유실이나 누수를 발견한 것이 아니며, API의 의도된
계약에 위배되는 upstream 버그인지까지 확정하지 않는다.
