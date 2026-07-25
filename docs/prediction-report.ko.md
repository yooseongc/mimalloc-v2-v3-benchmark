# 장기 멀티스레드 프로그램용 mimalloc v3.4.3 도입 예측 보고서

작성일: 2026-07-25  
대상: allocation/free가 매우 빈번하고 장기간 실행되는 멀티스레드 프로그램  
비교: mimalloc v2.1.2 (`43ce4bd7fd34bcc730c1c7471c99995597415488`) / v3.4.3 (`152fbf2634aeafca3774df791b0a77683035f076`)

## 결론 요약

v3.4.3은 이 용도에서 **우선적으로 canary 검증할 가치가 높은 후보**다. 특히 thread 생성·종료 또는 소유 thread가 끝난 뒤 다른 thread가 객체를 해제하는 패턴이 실제 서비스에 충분히 있다면, v2.1.2보다 장기 메모리 재사용과 처리량 안정성이 좋아질 가능성이 있다.

이 예측의 근거는 두 가지다.

1. 최종 측정에서 `thread_churn`은 THP `madvise`에서 v3/v2 중앙 처리량 비율 1.309, THP `never`에서 1.315를 보였다. 반면 일반 local mixed-wide와 4:4 remote-free 핵심 cell은 대체로 동등성 범위를 포함했다.
2. v3 소스는 abandoned page를 arena bitmap으로 추적하고, free 경로에서 조건부 page reclaim을 시도하며, reclaim 양을 제한하는 정책을 갖는다. 이는 오래 실행되며 thread lifecycle과 cross-thread free가 반복되는 상황에 직접 관련된 구조다.

다만 “v3가 반드시 더 낮은 RSS를 유지한다” 또는 “모든 다중 스레드 프로그램에서 더 빠르다”는 예측은 할 수 없다. 현재 측정에는 시간·일 단위의 soak run, true peak RSS 시계열, timed-process `AnonHugePages`, 프로덕션 allocation-size trace가 없다. 따라서 권고는 즉시 전면 교체가 아니라 **동일 정책의 staged canary와 장기 관측**이다.

## 1. 판단 범위와 증거 등급

| 주장 | 등급 | 근거 |
|---|---|---|
| thread churn이 많은 조건에서 v3가 유리할 가능성 | 높음 | r12/r13에서 일관된 약 1.31× 중앙 처리량 비율 + v3 reclaim 경로 |
| 안정적인 장기 RSS가 개선될 가능성 | 중간 | v3의 abandoned-page reclaim·purge 구조는 관련 있으나 장기 RSS 추세는 미측정 |
| 일반 local allocation/free 처리량이 개선될 가능성 | 낮음~중간 | fixed-small 8-thread는 v3 우위, mixed-wide는 거의 동등 |
| remote-free 처리량이 일관되게 개선될 가능성 | 낮음 | 최종 4:4 remote-free 신뢰구간이 동등성 1을 포함 |
| large allocation 성능이 개선될 가능성 | 낮음 | THP=madvise cell은 매우 높은 변동성, THP=never에서는 동등 |
| upstream default로 바로 교체해도 같은 효과 | 낮음 | v2 기본 purge delay는 10 ms, v3 기본값은 1000 ms로 정책이 다름 |

여기서 “높음”은 이 저장소의 제한된 환경과 workload에 대해서다. 애플리케이션 수준의 SLA·RSS 예산을 만족한다는 보증은 아니다.

## 2. 지금까지의 실측이 말하는 것

최종 데이터는 고정된 물리 코어 cpuset `0,2,4,6,8,10,12,14`, NUMA node 0에서 얻었다. r12는 THP=`madvise`, r13은 승인된 controller로 THP=`never`를 적용하고 원상 복구를 확인한 결과다. 각 보고 block에는 유효한 v2/v3 쌍 15회가 있다.

### 성능 관점

- `thread_churn`은 v3에 가장 일관된 우위를 보였다. 이는 장기간 실행 중 worker가 계속 생기고 사라지거나, 종료된 thread가 남긴 allocation의 free가 이어지는 서비스에 긍정적인 신호다.
- fixed-small local 8-thread도 v3가 1.032배(95% CI 1.024–1.047)로 높았다. 다만 mixed-wide local 1/8-thread는 각각 0.990 및 0.998로 거의 동등했다.
- 4 producer : 4 consumer remote-free의 fixed-small 및 mixed-wide는 중앙값이 v3에 약간 유리했지만 신뢰구간이 1을 포함한다. 즉, cross-thread free가 있다는 사실만으로 v3의 안정적인 처리량 우위를 예측할 수는 없다.
- `realloc`과 C++ `new/delete` 보조 API는 v3 우위를 보였지만 별도 harness revision 결과이므로 primary `malloc/free`와 합산하지 않는다.

### 메모리 안정성 관점

`burst_purge`, `lifetime_mix`, `thread_churn`, `large_alloc`은 장기 메모리 거동을 탐색하는 proxy다. 그러나 현재 local/remote harness의 `peak_rss_bytes`는 측정 중 최고치를 계속 sampling한 값이 아니라 측정 후 관측값을 기록하는 경로가 있다. 따라서 “v3의 peak RSS가 더 낮다”는 결론을 이 데이터만으로 내리지 않는다.

THP=`madvise`에서 large allocation의 v3/v2 중앙 처리량 비율은 2.334였지만 v3 측 변동계수가 약 51%였다. THP=`never`에서는 1.002로 동등했다. 이 결과는 v3가 큰 allocation에서 항상 우위라는 증거가 아니라, page policy·fault·touch 패턴의 영향을 별도 관찰해야 한다는 신호다.

## 3. 코드 차이에서 보는 예측 근거

### 3.1 v2: abandoned **segment**를 찾고 통째로 reclaim하는 경로

v2의 `src/segment.c`는 abandoned segment를 pop한 뒤 segment 안의 slices/pages를 순회하여 적합한 page를 reclaim한다. 한 번의 allocation에서 시도 횟수도 제한한다.

```c
long max_tries = mi_option_get_clamp(mi_option_max_segment_reclaim, 8, 1024);
while ((max_tries-- > 0) && ((segment = mi_abandoned_pop()) != NULL)) {
  bool is_suitable = _mi_heap_memid_is_suitable(heap, segment->memid);
  bool has_page = mi_segment_check_free(segment, needed_slices, block_size, tld);
  if (segment->used == 0) {
    mi_segment_reclaim(segment, heap, 0, NULL, tld);
  }
  else if (has_page && is_suitable) {
    return mi_segment_reclaim(segment, heap, block_size, reclaimed, tld);
  }
}
```

이 접근은 v2에서도 abandoned memory를 재사용한다. 따라서 v2가 thread 종료 뒤 메모리를 방치한다고 보는 것은 틀리다. 다만 reclaim 후보 탐색과 segment 단위 복구라는 구조는, partial live object가 많이 남는 장기 churn 상황에서 페이지 단위의 더 세밀한 정책과 다른 비용·재사용 양상을 만들 수 있다.

### 3.2 v3: abandoned **page**의 free 시점 reclaim과 상한

v3의 `src/free.c`는 abandoned page에서 free가 일어날 때, page를 즉시 free·reclaim·reabandon 중 하나로 처리한다. small/medium object page에 대해서는 reclaim-on-free 정책을 확인한다.

```c
if (mi_abandoned_page_try_free(page)) return;
if (page->block_size <= MI_MEDIUM_MAX_OBJ_SIZE && reclaim_on_free >= 0) {
  if (mi_abandoned_page_try_reclaim(page, reclaim_on_free)) return;
}
if (mi_abandoned_page_try_reabandon_to_mapped(page)) return;
mi_abandoned_page_unown_from_free(page, mt_free);
```

reclaim은 무제한으로 하지 않는다. originating thread의 heap인지, cross-thread reclaim이 허용됐는지, page가 너무 많이 사용 중인지, 현재 heap이 해당 size class page를 이미 많이 보유하는지를 확인한다.

```c
if (max_reclaim >= 0 &&
    !mi_page_queue_len_is_atmost(theap, page->block_size, max_reclaim)) {
  return false;
}
_mi_arenas_page_unabandon(page, theap);
_mi_theap_page_reclaim(theap, page);
```

공개 option 정의도 이 의도를 드러낸다.

```c
mi_option_page_reclaim_on_free,       // -1: 금지, 0: originating theap만, 1: 항상 허용
mi_option_page_max_reclaim,           // 같은 originating theap의 reclaim 상한
mi_option_page_cross_thread_max_reclaim // cross-thread reclaim 상한
```

이는 장기 프로그램의 두 상충 목표를 함께 고려한 설계다.

- 장점 예상: 종료된 thread의 page에서 늦게 free되는 객체가 있을 때, suitable page를 다시 소유해 atomic-heavy remote-free 상태를 줄이고 재사용 기회를 늘릴 수 있다.
- 비용·위험 예상: reclaim을 너무 공격적으로 하면 한 thread가 page를 오래 보유하여 thread 간 재사용을 줄이고 RSS/fragmentation이 나빠질 수 있다.

v3 소스 주석도 이 trade-off를 직접 설명한다. 그래서 기본값은 cross-thread free에서 무제한 reclaim이 아니라 제한적이며, 실서비스에서 이 옵션을 무작정 `1`로 켜는 것은 추천하지 않는다.

### 3.3 v3 arena bitmap과 재사용 후보 탐색

v3 `src/arena.c`는 abandoned page를 size-class별 bitmap으로 찾고 claim한다.

```c
if (mi_bitmap_try_find_and_claim(bitmap, tseq, &slice_index,
                                 &mi_arena_try_claim_abandoned, arena)) {
  mi_page_t* page = mi_arena_page_at(arena, slice_index);
  mi_atomic_decrement_relaxed(&heap->abandoned_count[bin]);
  mi_theap_stat_counter_increase(theap, pages_reclaim_on_alloc, 1);
}
```

이 구조는 thread 종료가 자주 발생하고 다양한 size class의 live object가 남는 workload에서, 적합한 page를 찾는 동시성·재사용 효율을 개선할 가능성을 제공한다. thread churn 실측 우위는 이 예상과 정합적이다. 하지만 benchmark는 allocator 내부 reclaim counter를 primary timed run에서 수집하지 않았으므로, 관측된 우위의 단일 원인을 bitmap reclaim으로 확정할 수는 없다.

### 3.4 purge 기본값은 성능·RSS 해석의 가장 큰 교란 요인

두 버전은 `purge_delay`의 **단위는 모두 밀리초**지만, 기본값과 arena multiplier가 다르다.

```c
// v2 src/options.c
{ 10,   UNINIT, MI_OPTION_LEGACY(purge_delay,reset_delay) },

// v3 src/options.c
{ 1000, MI_OPTION_UNINIT, MI_OPTION_LEGACY(purge_delay,reset_delay) },
```

일반 option 기본값은 v2 10 ms, v3 1000 ms다. 또한 arena의 실제 지연은 두 버전 모두 `purge_delay × arena_purge_mult`로 계산된다. v2의 기본 multiplier는 10이므로 기본 arena 지연은 약 100 ms이고, v3의 기본 multiplier는 1이므로 약 1000 ms다. 즉 단위 변환이 아니라 기본 정책이 다르다.

v3의 더 긴 기본 delay는 재사용 직후 decommit/recommit을 피하여 장기 server의 fragmentation과 성능을 개선할 수 있지만, 짧은 관측창에서는 RSS가 더 오래 유지되는 것처럼 보일 수 있다. 이것은 allocator 구현 우위와 upstream default policy 효과를 분리해야 하는 이유다.

이번 normalized purge 비교에서 `MIMALLOC_PURGE_DELAY=-1`, `0`, `1000`의 v3/v2 처리량 비율은 거의 1이었다. 특히 delay 0은 두 버전 모두 절대 처리량을 낮췄다. 따라서 서비스의 메모리 예산이 엄격하다면 “v3 기본값 그대로”와 “v2와 의미상 동일한 purge policy”를 반드시 별도 canary로 평가해야 한다.

### 3.5 THP 친화 purge는 조건부 이점이다

v3 `src/arena.c`는 purge할 최소 단위를 계산해 bitmap range를 처리한다.

```c
const size_t minslices = mi_slice_count_of_size(_mi_os_minimal_purge_size());
_mi_bitmap_forall_setc_rangesn(arena->slices_purge, minslices,
                               &mi_arena_try_purge_visitor, arena, &vinfo);
```

`minimal_purge_size`의 기본 해석은 THP 허용 설정에 따라 달라질 수 있다. 따라서 THP=`madvise` 아래의 large allocation 결과를 THP=`never` 또는 컨테이너/호스트가 다른 환경으로 일반화하면 안 된다. 이번 실험도 이를 반영해 두 THP 상태를 별도 block으로 다뤘다.

## 4. 워크로드별 예측

| 실제 프로그램의 특성 | v3.4.3 예측 | 근거와 주의점 |
|---|---|---|
| 고정 크기 작은 객체, 같은 thread allocate/free, 높은 병렬도 | 약한~중간 성능 개선 가능 | fixed-small local 8-thread v3 우위. 다른 size profile에서는 동등 가능 |
| 크기가 넓게 섞인 local allocation | 대체로 동등 예상 | mixed-wide local 1/8-thread가 동등 범위 |
| producer/consumer 간 remote free가 지속 | 동등~약한 개선 가능 | 4:4 remote-free는 결론적 우위가 아님. queue 및 실제 topology가 중요 |
| thread pool은 유지되나 task만 교체 | 작은 차이 또는 workload 의존 | thread termination이 적으면 abandoned-page 이점이 덜 직접적 |
| worker가 자주 종료·재생성되고 살아남은 객체가 다른 thread에서 해제 | 중간~높은 개선 가능 | thread-churn 실측과 v3 reclaim-on-free 구조가 직접 관련 |
| 버스트 뒤 긴 idle, RSS 예산이 엄격 | 정책에 따라 달라짐 | v3 default purge 1000 ms가 재사용에는 유리할 수 있으나 관측 RSS는 높을 수 있음 |
| 대형 객체·THP·page fault가 지배 | 예측 불가 | 현재 큰 ratio의 변동성이 높고 실제 THP 사용량이 미확인 |

## 5. 도입 권고

### 권고: v3.4.3 canary 도입, 단 기본 정책 전면 적용은 보류

다음 조건을 만족하면 v3.4.3을 제한된 인스턴스에서 먼저 사용해 볼 만하다.

- 프로세스가 수 시간 이상 살아 있고, allocation/free가 많으며, thread churn 또는 종료 thread 객체의 늦은 free가 실제로 있다.
- 현 v2.1.2에서 RSS의 우상향, 높은 allocator 관련 CPU, pause/tail latency 악화 중 하나가 관찰된다.
- canary와 rollback에서 allocator shared library와 관련 환경 변수를 명시적으로 통제할 수 있다.

### 설정 원칙

1. 첫 canary는 v2 production과 **동일한 THP 상태, cpuset/NUMA 정책, memory limit, `MIMALLOC_PURGE_DELAY`**를 사용한다.
2. 그 다음에만 v3 upstream-default purge policy를 별도 실험한다. 이 단계의 RSS와 처리량은 normalized 비교 결과와 섞지 않는다.
3. `MIMALLOC_PAGE_RECLAIM_ON_FREE=1` 같은 공격적 cross-thread reclaim 설정은 baseline에서 제외한다. 앱 trace가 cross-thread free·thread churn에 치우쳤고 canary 지표가 개선되지 않을 때만 별도 one-variable 실험으로 검토한다.
4. HugeTLB, cross-NUMA, large OS page는 본 프로젝트의 승인된 범위 밖이다. 이들의 효과를 기대해 배포 정책을 바꾸지 않는다.

## 6. 장기 canary에서 판정할 지표

최소 24시간, 가능하면 실제 traffic 주기 하나 이상을 포함해 다음을 버전별·동일 정책별로 비교한다.

| 범주 | 필수 지표 | v3 채택 판단 예 |
|---|---|---|
| 처리량 | 요청/초, allocation/free 관련 작업/초, CPU time/요청 | 동일 SLA에서 v2보다 악화하지 않음 |
| 지연 | p50/p95/p99/p99.9, 최대값, 시간대별 추세 | tail이 지속적으로 악화하지 않음 |
| RSS | VmRSS, VmHWM, cgroup memory.current/peak, 시간별 기울기 | working set 변화로 설명되지 않는 지속 우상향이 없음 |
| 반환 | burst 후 즉시·10 ms·1 s·60 s RSS, reclaim/purge 진단 | 서비스의 memory budget 안에서 회복 |
| VM/THP | minor/major faults, `AnonHugePages`, THP vmstat delta | page 정책 변경으로 인한 부작용이 없음 |
| 정확성 | crash, OOM, checksum, leak, allocator error log | v2 baseline보다 나쁘지 않음 |

RSS는 절대값 하나보다 **시간에 따른 기울기**, workload phase별 plateau, v2와 v3의 동일 traffic 구간 비교가 중요하다. v3의 더 긴 purge delay는 순간 RSS를 높일 수 있어도 later reuse의 page fault와 CPU를 줄일 수 있다. 따라서 RSS만 낮은 쪽을 자동으로 “메모리 안정적”이라고 판단하지 않는다.

## 7. 명시적 반증 조건과 rollback 기준

다음 중 하나가 확인되면 v3 canary를 중단하거나 v2로 rollback하고 원인을 분리한다.

- 같은 traffic/정책에서 cgroup peak 또는 RSS 추세가 반복적으로 memory budget을 침범한다.
- p99/p99.9 latency 또는 CPU/요청이 실질적으로 악화하고, host load·THP·cpuset 차이로 설명되지 않는다.
- allocator validation, checksum, pointer accounting, crash/OOM 중 하나가 발생한다.
- v3의 우위가 `MIMALLOC_*` 환경 변수 차이 또는 다른 binary/library hash에만 의존함이 드러난다.

반대로, thread churn/cross-thread free가 많은 실제 traffic에서 RSS 추세가 동등하거나 더 안정적이고 tail latency·CPU가 악화하지 않으며, 최소 하나의 traffic 주기 동안 오류가 없다면 v3.4.3을 확대할 근거가 생긴다.

## 8. 최종 예측

이 프로젝트의 원래 목적—매우 오래 실행되고 메모리 할당·해제가 많은 멀티스레드 프로그램에서 v3.4.3이 v2.1.2보다 성능과 메모리 안정성을 높일지 판단—에 대해 다음처럼 예측한다.

> **thread lifecycle과 cross-thread object lifetime이 실제로 중요한 프로그램이라면 v3.4.3은 성능과 장기 메모리 재사용 측면에서 v2.1.2보다 나아질 가능성이 높다.**
>
> **그러나 일반적인 다중 스레드 local churn 또는 remote-free만으로는 일관된 우위를 보장하지 않으며, v3의 긴 기본 purge delay 때문에 단기 RSS가 더 낮아질 것이라고도 예측할 수 없다.**

따라서 가장 합리적인 운영 결정은 “v3를 동일 정책으로 canary한 뒤, long-run RSS 기울기·tail latency·CPU·오류율을 통과 기준으로 확대 여부를 결정한다”이다.

## 관련 자료

- [확정 정량 보고서](experiment-report.md)
- [코드 분석 기반 정성 보고서](qualitative-code-analysis.ko.md)
- `extern/mimalloc-v2.1.2/src/segment.c`
- `extern/mimalloc-v2.1.2/src/options.c`
- `extern/mimalloc-v3.4.3/src/free.c`
- `extern/mimalloc-v3.4.3/src/arena.c`
- `extern/mimalloc-v3.4.3/src/options.c`

이 문서는 확정된 실측 결과와 고정된 두 upstream source tree를 바탕으로 한 예측이다. 새 장기 측정을 수행하지 않았으며, 측정하지 않은 메모리 안정성 수치를 생성하지 않았다.
