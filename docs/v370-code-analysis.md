# v3.7.0 변경과 관찰 범위

**성능 후속 분석 결론:** 256 KiB는 내부 large-page 기본값 변경에 따른
**다중 블록 페이지 → singleton 페이지 전환**이 가장 강한 원인 후보다.
4 KiB는 같은 페이지 분류를 유지하지만 일반 할당 경로의 **theap cookie 검사**,
free-list 확장과 원격 해제 수집의 코드 생성이 달라졌다. 이 비용이 측정 저하분을
얼마나 설명하는지는 아직 인과 검증하지 않았다. 상세 근거와 반증 조건은 아래 후속 절에 있다.

2026-11-18. v3.6.1 `56dc5eb8`과 v3.7.0 `1ed67b51`의 원본 소스를 비교했다.
아래는 코드 관찰이며, 실행 결과의 원인을 확정하는 자료는 아니다.

## purge 예약과 실행의 동기화

`src/arena/arena-alloc.c`의 `mi_arena_schedule_purge`는 v3.6.1에서 만료 시각을
CAS로 등록한 뒤 purge bitmap을 설정했다. v3.7.0은 bitmap을 먼저 설정하고,
0을 미설정으로 취급하는 atomic minimum 연산으로 arena와 subproc 만료 시각을 갱신한다.

`mi_arena_try_purge`와 `mi_arenas_try_purge`의 만료 시각 초기화는 store에서
acquire-release exchange로 바뀌었다. 아직 실행 시각이 되지 않은 arena의 가장 빠른
만료 시각을 `pending_expire`에 보존해 다시 등록한다. 방문 제한 때문에 모두 처리하지
못한 경우에도 다음 시도에 이어갈 수 있도록 예약을 남긴다.

이는 예약자가 기록한 작업과 purger가 만료 시각을 지우는 작업 사이의 순서를 다루는
변경이다. 단순히 purge_delay 기본값을 줄인 변경이 아니다. 이번 기본 및 delay 정렬
비교는 RSS 패턴을 관찰하지만 이 경쟁 조건을 의도적으로 재현하거나 수정만을
되돌린 A/B 비교가 아니므로, 관찰한 RSS 차이를 이 수정의 단독 효과로 부르지 않는다.

## realloc 축소

`include/mimalloc/alloc/alloc.h`의 `mi_realloc_is_in_place`는 일반 블록의
in-place 유지 기준을 usable size의 7/8 이상으로 둔다. v3.6.1의 1/2 기준과 다르다.
huge singleton page에는 새 크기가 large 한계보다 크고 원래 크기의 절반 이상이며
tail reset이 가능할 때의 예외가 있다. `mi_realloc_shrink_in_place`는 huge 블록의
줄어든 뒤쪽에 reset을 요청한다. reset은 RSS가 즉시 줄어든다는 뜻이 아니다.

일반/정렬 realloc 경로가 이 공통 판단을 사용하고 같은 heap인지도 확인한다.
기존 [realloc 진단](realloc-20261110-report.md)은 개발 커밋의 기준 변경과 tail reset을
분리한 실험이다. 이번 공식 v3.7.0에서는 해당 API를 다시 측정하지 않았으므로 기존
수치를 v3.7.0 수치로 옮기지 않는다.

## 해석

동시 처리량은 쓰기·동기화·검증·해제까지 포함한다. 보안 기능용 내부 구조 변경도
있지만 MI_SECURE=OFF의 비용 변화가 어느 코드에서 왔는지는 버전 비교만으로
판정할 수 없다. 하드웨어 보안 기능의 지원 여부와 일반 Release 성능은 별개다.

근거: [고정 소스](https://github.com/microsoft/mimalloc/tree/1ed67b5156a763441d2ec3c20221a7b3cd866129),
로컬 원본 두 checkout, experiments/release-v370-v1/source-diff-evidence.json.

## 성능 후속: 조사 방법과 증거 수준

사용자 요청에 따라 2026-11-18 정성 분석을 추가했다. 원본 소스와 성능 실험의 동결
실행기·계획·raw는 수정하지 않았다. 기존에 측정한 두 shared library의 SHA-256을
artifacts.json과 대조하고, 동일 Rocky 이미지/GCC/flags로 상수·구조체 배치와
단일 할당의 내부 페이지를 확인했다. 추가 성능 benchmark나 수정 빌드 A/B는 하지 않았다.

증거는 `experiments/v370-code-analysis-v1/`에 있다:

- `inspect.py`, `layout.c`, `evidence.json`: 컴파일 플래그, 상수, 구조체 배치, 소스와 library hash.
- `inspect_pages.py`, `pages.c`, `pages.json`: 버전당 네 크기를 한 번씩 할당하고 해제한 구조 관찰.
- `v3.6.1-selected-assembly.txt`, `v3.7.0-selected-assembly.txt`: 실제 성능 측정 library의 명령어.
- `*-macros.txt`, `*-assembly.txt`: 전처리와 전체 disassembly. 진단 바이너리는 성능 표본이 아니다.

두 빌드 모두 MI_SECURE=0, MI_STATS=1, MI_PROFILE=1이다. v3.6.1에서는
MI_SECURE의 헤더 기본값이 0이고 v3.7.0에서는 컴파일 옵션에도 0이 명시됐다.
v3.7.0에서 PAC=0, QSBR=0, secure reuse delay=0이며 MTE 경로도 비활성이다.
따라서 암호화 free-list, MTE 태깅, secure hold-back의 실행 비용으로 설명하면 안 된다.
그러나 **일반 빌드에도 남는 핸들 검사는 별개**다.

## 1. 256 KiB: 페이지 관리 단위가 바뀌었다

`include/mimalloc/types.h`의 MI_ENABLE_LARGE_PAGES 기본값이 1→0으로 바뀌었다.
이것은 mimalloc 내부 4 MiB 페이지의 사용 정책이며 Linux THP/HugeTLB와 다르다.
동일 빌드 플래그로 평가한 값은 다음과 같다.

| 항목 | v3.6.1 | v3.7.0 |
|---|---:|---:|
| MI_ENABLE_LARGE_PAGES | 1 | 0 |
| MI_SMALL_MAX_OBJ_SIZE | 10,240 B | 10,240 B |
| MI_MEDIUM_MAX_OBJ_SIZE | 86,698 B | 81,920 B |
| MI_LARGE_MAX_OBJ_SIZE | 524,288 B | 81,920 B |

실제 원본 library의 단일 할당을 확인한 결과도 분기와 일치했다.
reserved는 그 페이지가 수용하도록 예약한 블록 수이며, 전부 커밋하거나 사용 중이라는 뜻이 아니다.

| 요청 크기 | v3.6.1 내부 영역 / reserved | v3.7.0 내부 영역 / reserved |
|---|---|---|
| 4 KiB | 64 KiB / 15 | 64 KiB / 15 |
| 16 KiB | 512 KiB / 31 | 512 KiB / 31 |
| 64 KiB | 4 MiB / 63 | 512 KiB / 7 |
| 256 KiB | 4 MiB / 15 | 320 KiB / 1 |

256 KiB의 새 경로는 `mi_find_page → mi_huge_page_alloc → _mi_page_fresh_alloc →
_mi_arenas_page_alloc → mi_arenas_page_singleton_alloc`이다. 여기서 huge는 내부
분류이며 매번 OS mmap 또는 HugeTLB를 쓴다는 뜻이 아니다. arena의 64 KiB slice를 이용할 수 있다.

기존에는 하나의 4 MiB 페이지가 여러 256 KiB 블록을 제공하고 원격 free 목록과 페이지
관리를 여러 객체가 공유했다. 새 경로는 객체마다 페이지 초기화·등록과 full/abandon 처리를
거치며, 원격 해제에서 singleton이 비면 페이지 반환 경로로 이어진다.
`mi_free_try_collect_mt`는 이 크기에서 일반 thread-free 수집을 수행하고
`mi_abandoned_page_collect_empty`를 먼저 시도한다. 단일 블록을 비울 때마다
페이지 수준의 작업이 필요해지는 구조가 주요 차이다.

singleton 할당은 cache offset 여유분을 추가한 뒤 slice 단위로 올림한다.
이 빌드에서 256 KiB + 여유분은 5 slices=320 KiB로 관찰됐다. 이는 예약 공간의
증가 요인이지만 추가 영역을 모두 touch하는 것은 아니므로 25%가 그대로 RSS 증가가 되지는 않는다.
실제 원격 실행에서 페이지 생성·반환 횟수를 계측하지 않았으므로 관리 횟수 증가의 정량값은 주장하지 않는다.

관찰과의 부합:

- 동일 바이트 비교에서 256 KiB 처리량은 187.64→113.34 GiB/s, 약39.6% 감소했다.
- 작업 중 RSS 중앙값은 18.90→28.20 MiB, 작업 중 minor fault 중앙값은 12→4,425였다.
- producer CPU는 약2,585→4,305 ns/객체, consumer도 약2,585→4,307 ns/객체였다.
  두 CPU 시간은 쓰기·검증·spin 대기 등을 포함하므로 양쪽 allocator 함수가 각각 그만큼
  느려졌다는 뜻이 아니다. 한쪽 병목이 다른 쪽 대기를 늘릴 수 있다.

**판정:** 코드의 분기 전환과 기존 바이너리의 실제 페이지 배치까지 확인했다.
256 KiB에 집중된 큰 저하를 설명하는 최우선 가설이다. 다만 39.6% 전부가 이 변경 때문이라는
확정에는 동일 v3.7.0에서 이 정책만 복원한 별도 A/B가 필요하다.

근거: v3.7.0 `types.h:168,585`, `alloc/page.h:87`,
`src/alloc/alloc-generic.c:248`, `src/arena/arena-page-alloc.c:657,691`,
`src/alloc/free.c:746`. v3.6.1 대응 구현은 `src/arena/arena-page.c`에 있다.

## 2. 64 KiB는 왜 같이 느려지지 않았나

v3.6.1은 64 KiB 블록에 cache offset 공간을 주기 위해 medium 페이지 대신 large
페이지를 선택했다. `mi_block_size_is_medium`의 이 예외는 MI_ENABLE_LARGE_PAGES가
켜졌을 때만 적용된다. v3.7.0에서는 예외가 빠져 512 KiB medium 페이지를 사용한다.

따라서 64 KiB는 여전히 **여러 블록을 담는 페이지**다. 256 KiB의 singleton 전환과는
다르다. 이번에는 처리량이 184.62→193.33 GiB/s로 약4.7% 높았고 작업 중 RSS는
16.91→12.81 MiB로 낮았다. 더 작은 관리 영역과의 방향 일치는 있지만 캐시 miss나
페이지 재사용 횟수를 측정하지 않아 그것이 개선 원인이라고 단정하지 않는다.

16 KiB는 양쪽 모두 medium 페이지이며 처리량 차이는 약-1.7%였다.
이 크기별 경계가 256 KiB 회귀를 일반적인 memset 또는 모든 큰 할당의 문제로
설명하기 어렵게 만드는 근거다.

## 3. 4 KiB: 일반 할당 경로의 추가 검사와 확장 정책

### 매번 지나가는 theap cookie 검사

실제 `__libc_malloc` disassembly에서 양쪽 모두 요청 크기 `0x400`(1 KiB)까지는
직접 page lookup/pop 경로를 사용한다. 주소를 제외한 이 짧은 성공 경로의 명령어는 같다.
4 KiB는 이 범위를 벗어나 `_mi_malloc_generic`으로 들어간다.

v3.7.0 `alloc-generic.c:543`은 초기화 여부 다음에 `mi_theap_has_valid_cookie`를
검사한다. `heap/heap.h:33`에서 PAC가 꺼졌을 때도 프로세스 키와 핸들 주소를
`mi_mul_xor64`로 섞어 검증한다. 측정 바이너리의 `0x2258e–0x225a8`에는 키 load,
xor, `mul %rdi`, xor, cookie 비교와 조건부 분기가 실제로 존재한다.
v3.6.1 대응 지점에는 없다. 즉 소스에만 있는 비용이 아니라 최적화 후에도 남는다.

64 B·1 KiB도 페이지 보충 등으로 일반 경로에 들어갈 수는 있지만, 성공할 때마다
통과하는 4 KiB와는 호출 빈도가 다르다. 이 비대칭은 작은 객체보다 4 KiB에서
저하가 두드러지는 패턴과 맞는다. 명령어 수로 몇 ns 또는 몇 %를 추산하지는 않는다.

### free-list 확장을 8 KiB 경계에 맞춤

`_mi_page_extend_free`는 이전의 `8192 / block_size` 방식 대신, 현재 블록 주소에서
다음 8 KiB 경계까지의 공간으로 max_extend를 계산한다. 의도는 불필요한 OS 페이지
touch를 줄이는 것이다. 이 진단의 4 KiB 첫 블록은 slice 시작+4 KiB였고 최초
capacity가 2→1로 바뀌었다. 페이지 분류와 reserved=15는 그대로다.

첫 확장 비용을 더 적은 객체에 나눠 부담하고 보충 시점도 달라질 수 있다.
그러나 **모든 확장이 항상 2→1이거나 보충 횟수가 두 배라는 주장은 아니다**.
주소 정렬과 재사용·원격 free 도착 상황에 따라 달라진다. 기존 성능 실행의
page extension 횟수를 추가 수집하지 않았으므로 부차적인 원인 후보로 둔다.

### 원격 free 수집과 메타데이터 위치

`mi_page_thread_free_collect`가 명시적 CAS loop에서 atomic fetch-and 형태로 바뀌었다.
하지만 GCC 8.5/x86-64의 실제 결과는 여전히 `lock cmpxchg` 재시도 loop다.
따라서 소스상 acquire/release 차이만으로 락 연산이 사라졌거나 더 싸졌다고 말할 수 없다.
v3.7.0 `_mi_page_free_collect`는 목록 처리에 `mi_page_thread_collect_to_local`을
호출하고, v3.6.1의 대응 부분은 이 함수 안에 인라인되어 있다. 코드 배치와 호출 비용이
달라졌지만 실제 호출 빈도·CAS 재시도 수는 미측정이다.

메타데이터 인덱스도 직접 매핑에서 `slice_idx * 5 mod count`로 바뀌었다.
이는 캐시 배치를 바꾸므로 영향 방향이 정해져 있지 않다. 구조 진단에서 mi_page_t의
크기는 둘 다128 B, free/local_free/page_start/xthread_free 오프셋은 각각16/24/48/64로
같았다. 따라서 “보안 지원 때문에 이 빌드의 page 구조체가 커져서 느려졌다”는 설명은
근거와 맞지 않는다.

**판정:** 4 KiB는 cookie 검사가 가장 직접적인 hot-path 비용 증가 후보다.
확장 정책, 원격 목록 처리와 캐시 배치는 추가 후보다. 동일 바이트 비교의 producer
CPU 중앙값은 약193→213 ns/객체, consumer는 약62→64 ns/객체로 나타나지만
이 역시 순수 allocator 시간은 아니다. 기본 비교 -4.7/-6.8%와 별도 크기 비교 -11.6%를
하나의 원인별 기여율로 분해할 수는 없다.

## 4. 이번 성능 저하의 직접 원인으로 취급하지 않을 변경

- realloc 축소 정책: timed workload는 malloc/memset/free이며 realloc을 호출하지 않는다.
- MTE/PAC와 암호화 free-list: 이번 일반 빌드에서 해당 기능이 꺼져 있다.
- 큰 mi_page_t: 실제 sizeof와 주요 필드 배치가 동일하다.
- 단순 purge 기본값 변경: 두 버전의 delay1000/mult4 기본값은 같다. 단, 위에서 설명한
  purge 예약 알고리즘 자체의 변경은 동작에 영향을 줄 수 있다.
- RSS 감소를 무조건 효율 개선으로 해석: delay10/mult1에서 작업 중 생존량도
  21.50→0.12 MiB로 달랐다. producer/consumer의 진행 균형과 반환 동작을 분리해야 한다.

## 5. 인과 검증을 한다면

우선순위는 (1) 같은 v3.7.0의 MI_ENABLE_LARGE_PAGES=1 진단 빌드로 64/256 KiB 확인,
(2) cookie 검사만 바꾼 별도 소스 패치 A/B로 4 KiB 확인,
(3) 확장 정책·메타 인덱스·목록 수집을 각각 따로 비교하는 순서다.
첫 실험도 64 KiB 경로와 MI_MAX_RECLAIM_OBJ_SIZE 등 파생 상수를 함께 바꾸므로
단일 명령의 효과가 아닌 정책 묶음의 효과로 해석해야 한다.
공식 릴리스 결과와 수정 결과를 합치지 않고 새 namespace와 계획을 사용해야 한다.
이번 작업은 이 검증을 실행한 것이 아니라, 어떤 변수를 먼저 분리해야 하는지 좁힌 정성 분석이다.
