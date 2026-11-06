# v3.5.3: A 할당 전담 / B 해제 전담

Execution status: Complete
Date: 2026-09-22

**B가 실행한 free의 감소분 일부 또는 전부가 A의 통계에 계상됐다.** 전체 합계는
정확했지만, 스레드별 통계가 malloc/free를 실제 호출한 스레드의 실적과 일치하지 않았다.
이것은 “free 후 RSS가 아직 높다”는 관찰과 다른 내용이다.

## 조건

- v3.5.3 `d4881d338125e1cb7c47ba4cfb398d6f7c0c8d45`, 기존 기본 Release 라이브러리만 사용.
- A/B는 같은 독립 공유 heap에 각각의 theap을 연결한다. 시험 대상 객체는 A의
  `mi_malloc` 1,000회와 B의 `mi_free` 1,000회뿐이다. A free=0, B malloc=0을 검증한다.
- 64 B 및 4 KiB. B는 모든 객체 내용을 검증한 후 해제한다.
- 모든 checkpoint에서 A/B 둘 다 살아 있고, 각 스레드가 자기 통계를 읽는다.
  B가 종료하면서 통계를 병합하는 효과를 제외했다.
- 단계별로 진행을 정지해 읽으므로 읽기 경쟁은 없다. 동시 처리 성능을 측정한 것은 아니다.
- 출력 API와 stats reset은 사용하지 않는다. 실행기 자체의 메모리 할당은 시스템
  allocator를 쓰고, 시험 대상만 dlopen한 mimalloc의 명시적 API로 호출한다.
- 기본 자동 병합과 `MIMALLOC_COLLECT_MERGES_STATS=0`을 각각 실행했다.
  purge delay는 기본 1,000 ms이며 실제 option getter로 확인했다.
- A가 전체 할당 → A collect로 할당 통계 반영 확인 → B가 전체 해제 → B collect
  → A collect → 양쪽 collect 재확인 → 양쪽 명시적 merge 순서다.
  collect/merge는 업무 호출 수와 구분한 통계 확인 단계다.

## 해제량의 귀속

다음은 자동 병합을 끈 진단에서 **A/B 모두 수집을 끝냈고 아직 병합하지 않은 시점**이다.
수집을 한 번 더 해도 같았다. 두 번의 fresh process에서 같은 값을 확인했다.

`해제량`은 별도의 free 호출 카운터가 아니라 공개 필드
`malloc_normal.total - malloc_normal.current`로 계산한 bytes다.
동일 크기 객체이므로 괄호에 객체 수 환산값을 적었다.

| 객체 | A가 실제 해제 | B가 실제 해제 | A 통계에서 계산한 해제량 | B 통계에서 계산한 해제량 |
|---|---:|---:|---:|---:|
| 64 B × 1,000 | 0 B | 64,000 B | **64,000 B (1,000개분)** | **0 B** |
| 4 KiB × 1,000 | 0 B | 4,096,000 B | **163,840 B (40개분)** | **3,932,160 B (960개분)** |

64 B에서는 B가 전부 해제했는데 해제량이 전부 A에 잡혔다.
4 KiB에서는 B가 전부 해제했는데 A에 40개분, B에 960개분으로 나뉘었다.
따라서 이 값을 **호출 스레드 기준 해제 실적**으로 읽으면 실제 호출 기록과 다르다.

4 KiB의 같은 시점에서 A의 `current`는 +3,932,160 B이고 B의 `current`는
−3,932,160 B였다. 합계는 0이다. 이 양수/음수를 각각 실제 살아 있는 메모리나
누수량이라고 해석해서도 안 된다. 64 B에서는 A/B의 current가 모두 0이었다.

## 기본 설정에서는 어떻게 보이나

기본 자동 병합에서는 collect가 thread 통계를 상위 heap으로 옮긴다.
두 스레드가 모두 collect한 뒤에는 A/B 통계가 0이고 parent에 정확한 합계가 있었다.

64 B에서 B가 모두 해제하고 B만 collect했을 때에는 합계 current가 64,000 B로
남았고, A가 collect한 뒤에야 0이 됐다. 4 KiB에서는 B collect 후 163,840 B가
남았으며 A collect 후 0이 됐다. 어떤 스레드에서 수집하느냐도 반영 시점에 영향을 준다.

모든 조건에서 최종 합계는 할당 1,000개, 누적 할당·해제 각각 N×크기, current 0으로
정확했다. 2개 크기 × 2개 정책 × 2회 = 8개 프로세스가 객체 내용·호출 역할·최종 합계
검증을 모두 통과했다.

## 원인과 판단 범위

후속 [코드 분석과 page_full_retain 단일 변수 검증](thread-stats-ab-code-analysis.md)에서
40/960 분리의 원인을 확인했다. 4 KiB 객체는 페이지당 15개이며, 기본값은 full page
2개를 A에 보유한다. A에는 2×15+10=40개가 남고, 나머지 64×15=960개가 들어 있는
페이지는 abandoned가 되어 B 쪽에서 정산된다. 보유 수를 바꾼 10개 검증도 모두
사전 예측과 일치했다.

v3.5.3 `src/free.c:mi_free_block_mt`는 원격 free를 페이지의 atomic free 목록에
연결하고, 페이지가 abandoned 상태이면 해제자 쪽에서 회수할 수도 있다.
`src/page.c:mi_theap_page_update_stats`는 페이지의 할당 수·사용량으로 해제량을 계산한다.
`mi_theap_of_page`가 선택한 theap 또는 parent heap에 감소분을 반영하므로,
매 free 호출의 실행 스레드별로 따로 계수하는 구조와 다르다.

이번에 확인한 것은 **통계 귀속 방식이 호출 실적과 일치하지 않는다는 점**이다.
총집계의 통계 유실은 없었다. API가 호출 스레드별 실적을 보장하는지에 대한 계약 확인
없이 이를 곧바로 upstream 버그 확정으로 확대하지 않는다. 반대로 총합이 맞는다는
이유만으로 스레드별 호출량도 맞는다고 결론 내릴 수 없다.

이전 테스트는 B를 먼저 종료하고 A의 독립 heap과 다른 B의 기본 heap을 사용했다.
이번에는 같은 공유 heap, 두 theap의 생존 유지, 각자의 조회, 상위 heap의 미병합분을
명시적으로 분리했다. 따라서 이전 테스트의 B=0을 이번 모든 객체 크기에 일반화하지 않는다.

## 재현 자료

[C++ 테스트](../observation/thread_stats_ab.cpp) · [실행기](../observation/run_thread_stats_ab.py)
· [8개 실행의 전체 기록과 SHA](../experiments/thread-stats-ab-v353/results.json).

```powershell
docker run --rm --pull=never --network none --mount 'type=bind,source=C:\Users\user\workspace\mimalloc-test,target=/work' --workdir /work sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877 python3 observation/run_thread_stats_ab.py
```

기존 성능 측정 라이브러리·동결 설계·결과는 수정하지 않았다.
