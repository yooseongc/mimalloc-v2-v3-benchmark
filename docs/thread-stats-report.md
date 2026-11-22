# v3.5.3 스레드별 할당·해제 통계 재현

Execution status: Complete
Date: 2026-09-22

후속 요청에 따라 v3.5.3만 대상으로 A 할당 전담/B 해제 전담 및 양쪽 스레드 생존을
고정한 [통계 귀속 테스트](thread-stats-ab-report.md)를 추가했다. 해당 요청의 결론은
후속 보고서를 따른다.

**이 테스트로 스레드 통계 버그를 입증하지 못했다. 확인된 것은 지연 갱신과
집계 위치에 따라 조회값이 달라지는 동작이며, 최종 heap 집계의 통계 유실이나
메모리 누수는 재현되지 않았다.** 이를 단순히 “통계가 어긋났다”라고 표현해
버그의 근거처럼 제시한 것은 부정확했다.
스레드 통계는 실시간 호출 장부가 아니라 아직 상위 heap으로 병합되지 않은
통계 일부다. 페이지 단위 지연 갱신과 병합·회수 경로의 영향을 받는다.
이를 bug로 볼지는 API의 의도·보장 범위와 구분해야 하며, 특정 upstream 이슈가
수정 대상으로 인정됐다고 확인한 것은 아니다.

## 작은 테스트의 구성

새 A 스레드에서 독립 heap을 만들고 기본 theap으로 설정한 뒤 1,000개를 할당한다.
크기는 64 B 또는 4 KiB다. 각 객체를 실제로 쓰고 해제 전에 전체 내용을 검증한다.
A에서 해제하거나, B 스레드가 해제한 뒤 종료하고 A가 계속 살아 있는 경우를 나눈다.

`mi_theap_stats_get`을 A 자신에서 호출해 다음 단계를 읽는다.

1. 할당 전 → 할당 직후 → 같은 값을 다시 조회.
2. A가 `mi_collect(true)` 실행 → 스레드 통계 조회.
3. 전체 해제 → A가 다시 collect → 같은 collect를 한 번 더 수행.
4. 마지막에만 `mi_heap_stats_get`으로 상위 heap까지 합친다.

기본 설정과 `MIMALLOC_COLLECT_MERGES_STATS=0`을 분리했다. 후자는 진단용이다.
최종 통제 실행에서는 v3의 `mi_thread_stats_print_out`을 호출하지 않았다.
이 함수 자체가 통계를 병합하고 스레드 통계를 비우기 때문이다.

명시적 mimalloc API를 dlopen/dlsym으로 호출해 테스트 실행기의 std::thread·출력용
할당이 시험용 heap에 들어가지 않게 했다. 버전별로 해당 header를 사용해 빌드했고
version 및 library SHA를 기록했다. 성능 측정용 코드는 수정하지 않았다.

## 실제 결과

### 1. 할당 직후 조회는 일부 또는 전부가 빠진다

v3.5.3 기본 Release 라이브러리의 A 스레드 결과다. local/remote 시나리오는
이 단계까지 동일하게 재현됐다.

| 실제 작업 | 즉시 보고된 할당 개수 | 즉시 보고된 생존 bytes |
|---|---:|---:|
| 64 B × 1,000개 할당 | **0** | **0** |
| 4 KiB × 1,000개 할당 | **960** | **3,932,160** |

실제 생존 bytes는 각각 64,000과 4,096,000이다. 즉시 다시 조회해도 값은 같았다.
기본 설정에서는 collect 후에도 스레드 값이 0이었다. 누락분을 채운 통계가
상위 heap으로 병합되어 스레드 쪽이 비워지기 때문이다.

자동 병합을 끄고 collect하면 **두 크기 모두 정확히 1,000개 및 전체 생존 bytes**가
스레드 통계에 보였다. 따라서 초기 0 또는 960은 해당 시점의 지연 갱신으로 설명된다.

### 2. 해제 직후도 지연되며, 원격 해제는 collect만으로 해결되지 않는다

자동 병합을 끄고 출력 API도 호출하지 않은 대조 결과다.

| 흐름 | 모두 해제 직후 A의 current | A가 collect한 뒤 current | 최종 heap current |
|---|---:|---:|---:|
| 64 B, A가 해제 | 64,000 | 0 | 0 |
| 64 B, B가 해제 | 64,000 | 0 | 0 |
| 4 KiB, A가 해제 | 40,960 | 0 | 0 |
| 4 KiB, B가 해제 | 4,096,000 | **3,932,160** | **0** |

마지막 경우는 A가 collect를 다시 해도 3,932,160 bytes가 남았다. 동일한 fresh
process를 두 번 더 실행해 같은 값을 확인했다. B의 스레드 통계에는 해당 해제가
자신의 음수 current로 나타나지 않았다. 따라서 이것은 스레드별 free 호출 장부가 아니다.
상위 heap과 스레드 통계의 병합 결과는 정상이며, A의 current만 보면 잘못된
누수 판정을 내릴 수 있다.

### 3. 최종 집계는 이 범위에서 정확했다

v3.5.3의 2개 크기 × 2개 해제 방식 × 2개 병합 설정 모두에서:

- 누적 할당 개수: **1,000**
- 누적 할당 bytes: **64,000 또는 4,096,000**
- 현재 생존 bytes: **0**

이 세 조건은 코드에서 assertion에 해당하는 종료 조건으로 검증했다. 동일 스레드와
원격 해제 모두 전체 payload 검증도 통과했다. 최종 집계 검증이 통과했다는 것은
다른 수명·thread 종료·realloc·경합 상황에서도 통계 버그가 없다는 증명은 아니다.

## source와 일치하는 이유

고정 source는 v3.5.3 `d4881d338125e1cb7c47ba4cfb398d6f7c0c8d45`다.

- `src/page.c`의 `mi_theap_page_update_stats`는 페이지의 누적 할당 수와 사용량에서
  할당·해제 증분을 계산해 통계에 반영한다. 호출마다 모든 통계가 직접 갱신되는 방식이 아니다.
- `src/stats.c:mi_theap_stats_get`은 theap 통계를 복사하며 페이지의 미반영분을
  강제로 갱신하지 않는다.
- `src/options.c`의 `MI_DEFAULT_COLLECT_MERGES_STATS` 기본값은 1이다.
  `src/theap.c:mi_theap_collect_ex`는 수집 뒤 theap 통계를 상위 heap으로 병합한다.
- `src/stats.c:_mi_stats_merge_into`는 병합한 원본 통계를 초기화한다.
  deprecated `mi_thread_stats_print_out`도 출력 후 이 병합을 수행한다.
- 페이지 통계 갱신은 이용 가능한 theap 또는 상위 heap에 반영될 수 있다.
  원격 해제 후 스레드의 잔여 수치와 상위 집계를 분리해서 봐야 하는 이유다.
  이번 테스트는 내부 함수별 호출 횟수까지 계측하지 않았다.

따라서 **collect만 하면 스레드 통계가 항상 정확해진다**거나 **자동 병합만 끄면
스레드별 생존량을 얻는다**는 해결책도 이 테스트에서는 성립하지 않았다.
정확한 스레드별 malloc/free 호출 수가 필요하면 응용 측 계수를 별도로 두는 것이
이 API를 호출 장부로 해석하는 것보다 명확하다. heap 단위 집계가 목적이라면
이 테스트처럼 소유자가 수집한 뒤 합친 통계를 확인해야 한다.

## v2.1.2와 v3.5.0 참고 실행 및 검증상의 수정

두 버전도 제외하지 않고 같은 작은 흐름을 실행했다. 두 구버전의 기존 Release
기본 빌드는 `MI_STAT=0`이므로, **별도 진단 빌드에서 `MI_STAT=1`을 켰다.**
기존 성능 측정 라이브러리는 바꾸지 않았다. 3.5.3은 기존 기본 Release의
`MI_STATS=1` 라이브러리를 SHA 검증 후 그대로 사용했다.

v3.5.0은 64 B 할당 직후 byte 통계가 즉시 64,000으로 나왔다. 반면
`malloc_normal_count`는 이 진단 빌드에서 0이었다. 또 원격 free의 감소분이 B의
통계에 기록돼 독립 A heap만으로는 상쇄되지 않았다. v3.5.3과 계수·귀속 방식이
같다고 가정하지 않는다. v2.1.2는 새 structured theap API가 없어 기존 text 출력만
참고했고, 그 출력에는 thread/heap 준비 비용이 포함되어 64,000과의 정확한 일치를
assert하지 않았다.

초기 탐색에서는 deprecated 출력 API를 중간에 호출해 통계가 비워지는 효과를
함께 관찰했다. 또한 구버전에도 3.5.3과 같은 계수·heap 귀속을 기대해 v3.5.0의
4개 실행이 exit 10으로 끝났다. 이것을 구버전 버그나 3.5.3의 회귀로 판정하지 않았다.
초기 source·로그는 보존하고, 출력의 부작용과 버전별 assertion을 분리한 clean 실행을
최종 근거로 사용했다. clean 16개 프로세스 및 원격 해제 재확인 2개가 정상 종료했다.

## 재현과 자료

### purge delay 대조 확인

사용자 지적 후 같은 바이너리·라이브러리에서 `MIMALLOC_PURGE_DELAY=0`과 `-1`로
64 B local, 4 KiB remote, 자동 병합을 끈 4 KiB remote의 6개 프로세스를 실행했다.
비교한 통계 값은 두 설정에서 같았으며 최종 집계 검증도 모두 통과했다.
[추가 원자료](../experiments/thread-stats-v1/purge-control.json).
purge delay는 OS 메모리 반환 정책이며, 여기서 읽은 `malloc_normal.current`는
RSS/committed 통계가 아니다. 이번 조회값을 purge delay의 직접 효과로 설명할 근거는
없지만, 지연 갱신·통계 병합이라는 정상 동작을 오류와 구분하지 않은 점은 별개다.
이 대조 결과도 버그를 입증하는 것은 아니다.

[테스트 코드](../observation/thread_stats.cpp) · [빌드·실행기](../observation/run_thread_stats.py)
· [최종 기록](../experiments/thread-stats-v1/clean/results.json)
· [원격 해제 재확인](../experiments/thread-stats-v1/clean/remote-repeat.json).

```powershell
docker run --rm --pull=never --network none --mount 'type=bind,source=C:\Users\user\workspace\mimalloc-test,target=/work' --workdir /work sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877 python3 observation/run_thread_stats.py
```

이전 동시 처리 실험의 시간은 clock, RSS는 `/proc`에서 측정했다. 이번 스레드
통계의 지연·병합 현상 때문에 그 측정값이 직접 무효화되는 것은 아니다.
