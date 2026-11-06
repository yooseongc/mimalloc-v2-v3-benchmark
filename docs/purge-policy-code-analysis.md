# 동일 delay에서도 v3.5.0의 RSS가 낮은 이유

2026-10-24. 범위: purge-delay-v1에서 사용한 v3.5.0/v3.5.3/v3.6.0의
고정 소스·실제 빌드·기존 RSS 기록을 대조했다. 새 RSS 비교 실험은 실행하지 않았다.
실제 옵션을 읽는 작은 진단 프로그램만 세 라이브러리에 각각 실행했다.

코드에서 확인한 가장 직접적인 설명은 **THP 보존 정책에 따른 반환 단위 차이**다.
이번에 맞춘 delay와 arena 배수는 같지만, v3.5.0은 64 KiB 단위의 반환 후보도
처리하고 v3.5.3/v3.6.0은 통상 2 MiB로 정렬된 32개 slice가 모두 반환 후보인
경우에만 선택한다. 같은 시간 동안 기다려도 반환 가능한 영역의 양이 달라진다.
이 차이는 확인된 사실이며, 관측 RSS 격차의 가장 유력한 원인이다.
격차 전부 또는 몇 MiB가 이 정책 때문인지는 단독 변경 실험 없이 확정하지 않는다.

## 기본값과 실제 라이브러리 확인

| 항목 | v3.5.0 | v3.5.3 | v3.6.0 |
|---|---:|---:|---:|
| 실제 allow_thp | 1 | 2 | 2 |
| 실제 minimal_purge_size 옵션 | 0 (자동) | 0 (자동) | 0 (자동) |
| 진단 시 purge_delay / arena 배수 | 1000 / 1 | 1000 / 1 | 1000 / 1 |
| purge_decommits | 1 | 1 | 1 |
| OS 기본 page | 4 KiB | 4 KiB | 4 KiB |
| 자동 최소 반환 크기 계산 결과 | 4 KiB | 2 MiB | 2 MiB |
| arena에서의 선택 단위 | 64 KiB, 1 slice | 2 MiB, 32 slices | 2 MiB, 32 slices |

최소 반환 크기 계산 결과와 arena 선택 단위는 아래 코드에 실제 옵션·환경값을
대입한 값이다. 내부 함수를 직접 계측한 값은 아니다.

v3.5.0 `src/options.c:107`은 MI_DEFAULT_ALLOW_THP=1이다.
v3.5.3 `src/options.c:108`, v3.6.0 `src/util/options.c:113`은 2다.
v3.5.3 `CMakeLists.txt:612` 이후와 v3.6.0 `CMakeLists.txt:623` 이후는
Linux 기본 MI_ALLOW_THP=DEFAULT를 FULL로 해석하고 MI_DEFAULT_ALLOW_THP=2를 정의한다.
기존 빌드의 flags.make에도 각각 이 정의가 들어 있다. v3.5.0에는 override가 없어
소스 기본값 1이 적용된다. runtime getter 결과도 각각 1/2/2로 일치했다.

1은 THP를 허용하면서 purge가 THP를 쪼개는 것도 허용하는 정책이고,
2는 THP를 허용하면서 purge 선택 단위를 키워 쪼개짐을 줄이는 정책이다.
따라서 “v3.5.0은 THP를 사용하지 않는다”는 설명은 틀리다.

진단은 각 버전 헤더로 컴파일하고, 이전에 측정한 라이브러리의 SHA를 검증한 후
그 라이브러리를 명시적으로 로드했다. 결과와 커밋·SHA는
[runtime-options.json](../experiments/purge-policy-code-analysis/runtime-options.json)에 있다.
정확한 커밋은 3.5.0 `18b08671c9302247bfb682286e6bf3cc1773f801`,
3.5.3 `d4881d338125e1cb7c47ba4cfb398d6f7c0c8d45`,
3.6.0 `b18ab4eef383f655e760881b02eff8af02800879`다.

## 정책값이 실제 반환을 막는 경로

v3.5.3 `src/os.c:59`의 `_mi_os_minimal_purge_size()`는 다음 순서다.

```text
최소 반환 크기를 명시했으면 → 해당 크기
자동이고 THP 가능 + allow_thp == 2이면 → large page 크기
그 외 → OS 기본 page 크기
```

세 버전 모두 이 분기 구조를 사용한다. 이번 Linux 환경은 THP madvise다.
`src/prim/unix/prim.c:155`의 unix_detect_thp는 [never]가 아니면 true를 반환한다.
같은 파일 :82의 large page 크기는 이 플랫폼에서 2 MiB다.
따라서 3.5.0은 4 KiB, 이후 두 버전은 2 MiB로 계산된다.
이 판단은 각 주소가 현재 THP로 뒷받침되는지 검사하는 것이 아니라 전역 설정에 따른다.

v3.5.3 `src/arena.c:2406`은 이 크기를 arena slice 개수로 올림한다.
`include/mimalloc/types.h:235`의 slice는 64 KiB이고,
`include/mimalloc/internal.h:1379`는 divide-up을 한다.
그러므로 4 KiB는 1 slice, 2 MiB는 32 slices가 된다.
v3.6.0에서는 `src/arena/arena-alloc.c:497`에 같은 연결이 있다.

이 개수가 `_mi_bitmap_forall_setc_rangesn()`의 rngslices 인자가 된다.
v3.5.3 `src/bitmap.c:1517`, v3.6.0 `src/arena/bitmap.c:432`를 보면:

```c
if (rngslices <= 1) {
  return _mi_bitmap_forall_setc_ranges(...); // 개별 후보와 연속 후보를 처리
}
// 정렬된 rngslices 묶음마다 검사
if ((b & rngmask) == rngmask) {
  visit(...);  // 해당 묶음 전체가 purge 후보일 때만 실행
} else {
  skipped |= (b & rngmask);  // 일부만 후보이면 복원해서 남겨 둠
}
```

여기서 bitmap은 `slices_purge`, 즉 반환 예약된 영역이다. 후보로 선택된 다음에도
`mi_arena_try_purge_range()`는 `slices_free`에서 영역을 확보해 재할당되지 않았는지
확인한다. 따라서 free 호출 수나 비어 있는 바이트 합계만으로 반환량이 정해지지 않는다.

예를 들어 정렬된 2 MiB 안의 32개 slice 중 31개가 반환 후보이고 1개는 사용 중이라고
가정하자. v3.5.0의 선택기는 다른 조건도 충족하면 그 31개, 최대 1,984 KiB를
반환할 수 있다. 이후 버전의 32개 단위 선택기는 그 묶음을 건너뛴다.
이는 코드 동작을 설명하는 예시이며 실제 실행에서 이 배치를 계측했다는 뜻은 아니다.

선택 후 전체 free 영역 확보에 실패하면 slice별로 재시도하는 fallback도 있다
(`src/arena.c:2366` 부근). 따라서 “어떤 상황에서도 절대로 2 MiB보다 작게
purge하지 않는다”는 말은 부정확하다. 하지만 31개만 후보인 묶음은 애초에 visitor에
전달되지 않으므로 이 fallback이 위 예시를 해결하지는 않는다.

이 효과가 1 KiB 객체에도 적용된다. 객체 하나가 2 MiB라는 뜻이 아니다.
일반 1 KiB 객체는 작은 allocator page에 모이고, 그 page가 비어서 arena로 넘어온
다음 64 KiB slice 단위의 반환 후보가 된다(`src/arena.c:1194`, types.h:249).

## delay 구현 변경 때문인지 확인

v3.5.0과 v3.5.3의 `mi_arena_purge_delay()`부터 `mi_arenas_try_purge()`까지
예약·만료 검사·범위 확보·반환 실행 소스를 비교한 결과 텍스트가 동일했다.
`_mi_bitmap_forall_setc_rangesn()`도 동일했다. 비교 구간과 SHA는
[source-comparison.json](../experiments/purge-policy-code-analysis/source-comparison.json)에 남겼다.

즉 이 두 버전에서는 같은 선택 코드가 **서로 다른 기본값을 입력받아 다른 경로로
실행되는 것**이 확인된다. v3.6.0에도 위 선택 구조가 유지된다. 다만 v3.6.0에는
별도의 큰 영역 즉시 purge 조건 등이 있으므로 모든 반환 경로가 동일하다고 하지는 않는다.

## 기존 관측과 맞는가

delay=10 ms, arena 배수=1의 기존 3회 중앙값:

| 지표 | v3.5.0 | v3.5.3 | v3.6.0 |
|---|---:|---:|---:|
| 작업 중 RSS | 16.1 MiB | 74.0 MiB | 54.0 MiB |
| 완료 시 AnonHugePages | 0 MiB | 32 MiB | 52 MiB |
| 작업 중 minor page fault | 418,188 | 158,431 | 7,389 |

v3.5.0이 작은 빈 영역을 더 자주 반환하고, 이후 버전이 큰 페이지를 더 많이 유지하는
설명과 부합한다. 특히 AnonHugePages는 THP가 실제로 남아 있었음을 보여 준다.
다만 서로 다른 지표의 중앙값이 같은 실행에서 나온다고 가정해 빼거나 합치면 안 된다.
fault 수에는 재사용, THP의 fault 단위, 실제 생존량 등의 영향도 섞여 있다.
이 표만으로 모든 fault 차이 또는 RSS 차이를 THP 정책 하나에 귀속할 수는 없다.

Linux의 decommit 경로는 이번 purge_decommits=1에서 MADV_DONTNEED를 사용한다
(`src/os.c:676`, `src/prim/unix/prim.c:554`). 작은 빈 영역을 반환하면 RSS를 줄이는
데 유리하지만 다시 쓸 때 page fault 비용이 생길 수 있다. 반대로 THP를 보존하면
RSS를 더 유지하면서 큰 페이지의 이점과 재사용 여지를 남길 수 있다.
“RSS가 낮으므로 전체적으로 더 좋은 allocator”라는 결론까지 따라오지는 않는다.

## 원인 확정의 경계

확인한 것은 기본 정책 차이, 실제 라이브러리 적용값, 선택 알고리즘과 관측의 일치다.
전체 RSS 격차의 단독 원인이라는 검증은 아직 하지 않았다. page가 비는 시점,
회수·재사용, 처리 속도와 실제 생존량 차이도 남아 있다.

이 원인을 분리하려면 THP 자체와 delay는 유지한 채 반환 최소 크기만
세 버전 모두 64 KiB로 명시하는 대조가 적절하다. 3.5.0/3.5.3에서는
`MIMALLOC_MINIMAL_PURGE_SIZE=64`, 3.6.0에서는
`MIMALLOC_ARENA_PURGE_MIN_SIZE=64`가 해당한다. 숫자의 단위는 KiB다.
반대로 3.5.0에 2048을 적용해 RSS가 올라가는지도 보면 양방향으로 검증할 수 있다.
이번 요청에서는 코드 분석과 실제 옵션 확인까지 수행했고 이 대조 측정은 실행하지 않았다.
