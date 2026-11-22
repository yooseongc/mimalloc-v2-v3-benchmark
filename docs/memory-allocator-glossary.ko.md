# Linux 메모리와 mimalloc 용어집

이 문서는 이 저장소의 실험 보고서를 읽기 위한 한글 해설서다. Linux 메모리 지표와
mimalloc 내부 상태를 같은 말처럼 섞지 않고, `v2.1.2`와 `v3.4.3`의 실제 코드 구조를
구분해 설명한다.

이 문서가 기준으로 삼는 소스는 다음과 같다.

| 버전 | tag | 고정 commit |
|---|---|---|
| mimalloc v2 | `v2.1.2` | `43ce4bd7fd34bcc730c1c7471c99995597415488` |
| mimalloc v3 | `v3.4.3` | `152fbf2634aeafca3774df791b0a77683035f076` |

아래에서 **allocator page**는 mimalloc이 같은 크기의 객체를 담는 관리 단위이고,
**Linux page**는 커널의 가상 메모리 단위다. 둘은 이름만 같을 뿐 같은 것이 아니다.
일반적인 x86-64 Linux page는 4 KiB이고 THP page는 흔히 2 MiB이지만, 실제 크기는
호스트 설정과 아키텍처에서 확인해야 한다.

## 1. 한눈에 보는 전체 계층

```text
프로그램
  std::malloc / std::free
        │  LD_PRELOAD로 mimalloc 구현 선택
        ▼
mimalloc
  thread-local heap(v2) 또는 theap(v3)
        │
  allocator page ── segment(v2) / arena slice와 page map(v3)
        │
        ▼
Linux 가상 메모리
  mmap/munmap/madvise, 4 KiB page, THP(보통 2 MiB), HugeTLB
        │  처음 touch할 때 page fault와 zero-fill
        ▼
실제 자원
  RAM/NUMA node, CPU cache, TLB, memory bandwidth
```

창고에 비유하면 객체는 **상자**, allocator page는 같은 규격 상자를 모아 둔 **선반**,
segment나 arena는 여러 선반을 담는 **창고 구역**이다. `mmap`은 창고 부지를
확보하는 일, 첫 page fault는 그 부지에 실제 선반을 설치하는 일, purge는 빈 선반의
물리 자원을 OS가 다시 쓸 수 있게 하는 일에 가깝다.

비유에는 한계가 있다. Linux에서 `MADV_DONTNEED`로 purge하면 가상 주소라는 “부지”는
남은 채 현재의 물리 backing만 사라질 수 있다. `munmap`처럼 주소 범위 자체를 없애는
것과 다르다.

## 2. 공통 용어집

### 2.1 주소 공간과 메모리 사용량

| 용어 | 정의 | 내부 원리 | 결과를 읽는 법 |
|---|---|---|---|
| virtual reservation | 사용할 수 있는 가상 주소 범위를 확보한 상태 | Linux overcommit 환경에서는 `mmap`과 `MAP_NORESERVE`로 물리 RAM을 즉시 모두 확보하지 않고 주소부터 잡을 수 있다 | 큰 예약량만으로 RSS나 실제 RAM 사용량이 크다고 결론 내리지 않는다 |
| commit | allocator 또는 OS 관점에서 접근 가능한 backing을 준비한 상태 | Linux overcommit의 “commit”은 Windows의 물리 commit과 정확히 같은 뜻이 아니며, 실제 RAM은 첫 touch 때 붙을 수 있다 | mimalloc committed 통계, RSS, page fault를 함께 본다 |
| working set | 최근 실제로 접근해 계속 필요한 메모리 집합 | touch한 Linux page가 RAM에 resident하게 되고 재사용 패턴에 따라 유지된다 | live working set이 크면 purge가 정상이어도 RSS가 높다 |
| RSS | process에 현재 resident한 page의 합 | 공유 page도 process별 RSS에 잡히며 swap-out되거나 `MADV_DONTNEED` 처리된 page는 빠질 수 있다 | 가상 예약량이나 allocator의 live bytes와 같지 않다 |
| `VmHWM` | Linux가 기록한 process RSS의 high-water mark | `/proc/<pid>/status`가 process 수명 중 최대 resident 양을 기록한다 | 종료 시점의 `VmRSS`보다 true peak에 가깝지만 sampling·cgroup peak와 정의를 확인한다 |
| PSS | 공유 page 비용을 공유 process 수에 따라 나눈 비례 resident 크기 | shared library 같은 공유 page를 각 process에 전부 청구하지 않는다 | 여러 process의 실제 부담을 합산할 때 RSS보다 유용하지만 수집 비용이 더 크다 |
| retention | 해제된 논리 객체가 있어도 process RSS나 allocator 보유 공간이 당장 줄지 않는 상위 현상 | 빈 page 보유, retire 대기, purge delay, arena reservation, abandoned memory의 회수 시점이 합쳐진 결과 | mimalloc의 단일 상태명이나 곧바로 leak을 뜻하는 말로 쓰지 않는다 |

### 2.2 반환과 OS 호출

| 용어 | 정의 | 내부 원리 | 결과를 읽는 법 |
|---|---|---|---|
| `mmap` | 가상 주소 mapping을 만드는 syscall | anonymous/private mapping은 allocator가 큰 주소 범위를 얻는 일반 경로다 | 호출 수가 적어도 한 번에 큰 arena를 예약할 수 있다 |
| `munmap` | mapping 일부 또는 전부를 제거하는 syscall | 주소 공간과 backing의 관계를 끊는다 | RSS 감소를 만들 수 있지만 모든 purge가 `munmap`인 것은 아니다 |
| `madvise` | mapping 사용 의도를 커널에 알리는 syscall | `MADV_DONTNEED`는 backing 반환에, `MADV_HUGEPAGE`는 THP 요청에 쓰일 수 있다 | syscall 이름이나 총횟수만으로 purge인지 THP 요청인지 확정하지 않는다 |
| purge | allocator가 비어 있는 범위를 OS 재사용 후보로 만드는 정책 동작 | delay 뒤 decommit 또는 reset을 수행하며 arena의 예약 주소는 남을 수 있다 | purge 뒤 RSS 감소, system CPU 증가, 다음 접근 fault를 함께 본다 |
| decommit | 물리 backing을 적극적으로 버리는 purge 방식 | 이 두 버전의 Linux 기본 decommit 경로는 주로 `MADV_DONTNEED`를 사용한다 | RSS는 빨리 줄 수 있지만 재접근 때 zero-fill minor fault가 생길 수 있다 |
| reset | 내용이 더는 필요 없다고 알리는 더 느슨한 반환 의미 | 구현과 옵션에 따라 `MADV_FREE` 또는 fallback 경로가 가능하다 | 즉시 RSS가 줄지 않을 수 있으므로 decommit과 혼용하지 않는다 |
| release | 문맥에 따라 allocator 소유권 해제 또는 OS mapping 완전 반환을 가리키는 일반어 | source의 구체 함수가 page free인지 purge인지 `munmap`인지 확인해야 한다 | “release됨”만으로 주소 공간과 RSS가 모두 즉시 줄었다고 해석하지 않는다 |

### 2.3 page, fault, huge page

| 용어 | 정의 | 내부 원리 | 결과를 읽는 법 |
|---|---|---|---|
| allocator page | 동일 size class의 block을 관리하는 mimalloc 단위 | free list, 사용 block 수, 소유 heap/theap 같은 metadata를 가진다 | Linux 4 KiB page 수로 환산할 수 있는 단일 page로 오해하지 않는다 |
| Linux base page | 커널 page table이 관리하는 기본 page | 이 환경의 일반적인 값은 4 KiB지만 `getconf PAGESIZE`로 확인한다 | fault와 RSS는 이 OS 단위의 영향을 받는다 |
| THP | 커널이 anonymous memory를 큰 page로 backing하는 Transparent Huge Pages | x86-64에서는 흔히 2 MiB이며 `always`, `madvise`, `never` 정책과 mapping hint가 영향을 준다 | `AnonHugePages`, `THPeligible`, `thp_*` 변화로 실제 사용을 확인한다 |
| HugeTLB | 미리 예약한 hugetlb pool에서 명시적으로 얻는 huge page | `MAP_HUGETLB`나 전용 API·권한·예약이 필요하다 | `AnonHugePages`만으로 HugeTLB 사용을 증명할 수 없다 |
| minor fault | disk I/O 없이 page table/backing을 준비하는 fault | anonymous page 첫 touch의 zero-fill이나 purge 후 재접근에서 흔하다 | 수가 많으면 CPU 비용과 latency가 생길 수 있지만 major fault와 성격이 다르다 |
| major fault | storage I/O가 필요한 page fault | file-backed page나 swap에서 데이터를 읽어야 할 수 있다 | benchmark 중 발생하면 외부 I/O 잡음이나 메모리 압박을 의심한다 |

### 2.4 CPU와 성능

| 용어 | 정의 | 내부 원리 | 결과를 읽는 법 |
|---|---|---|---|
| TLB | 가상 주소→물리 주소 변환을 캐시하는 CPU 구조 | 큰 page는 같은 용량을 더 적은 translation entry로 덮을 수 있다 | THP는 TLB miss를 줄일 수 있지만 purge 단위와 RSS를 바꿀 수도 있다 |
| CPU cache | core 가까이에 데이터와 cache line을 보관하는 계층 | remote free의 atomic list 갱신은 page metadata cache line을 core 사이로 이동시킬 수 있다 | cache miss, coherence, topology가 allocator 차이와 섞인다 |
| user CPU | user mode에서 소비한 CPU 시간 | allocator의 일반 명령, queue, checksum, touch 비용이 포함된다 | elapsed와 함께 봐야 병렬 효율을 알 수 있다 |
| system CPU | kernel mode에서 소비한 CPU 시간 | syscall, page fault, zero-fill, scheduler 등이 포함된다 | 높다고 `madvise` 하나가 원인이라고 단정하지 않는다 |
| throughput | 단위 시간당 완료 operation 수 | 동일 operation count라면 elapsed의 역수 관계다 | 이 저장소의 paired `v3/v2 > 1`은 v3 처리량이 높다는 뜻이다 |
| tail latency | 느린 쪽 끝의 지연시간 분포 | p99, p99.9는 purge, fault, lock, scheduling의 드문 비용에 민감하다 | 평균이 좋아도 tail이 나빠질 수 있으며 sample 수와 sampling overhead를 확인한다 |

## 3. 메모리 생명주기: `free`에서 OS 반환까지

다음 용어는 서로 대체어가 아니라 서로 다른 단계다.

```text
malloc
  │
  ▼
live block ── free ──▶ allocator free list
                         │
                         ├─ 같은 page에서 즉시 재사용
                         │
                         └─ page 전체가 비거나 소유권 정책이 바뀜
                                  │
                     ┌────────────┼─────────────┐
                     ▼            ▼             ▼
                  retire       abandon       page free
                 잠시 보유     공유/무소유화    allocator 상위 단위로 반환
                     │            │
                     │         reclaim
                     │       다른/원래 실행 주체가 재소유
                     └────────────┴─────────────┐
                                               ▼
                                      purge delay 대기
                                               │
                                      decommit/reset
                                               │
                                      OS가 backing 재사용
                                               │
                                 주소 범위까지 끝내면 munmap
```

- `free`: block을 더 이상 live object로 쓰지 않는다고 allocator에 알린다. 보통 syscall은
  일어나지 않는다.
- `retire`: 완전히 빈 allocator page를 곧바로 해체하지 않고 가까운 재할당에 대비해 잠시
  보유한다.
- `abandon`: 사용 중 block이 남은 page를 현재 heap/theap의 독점 소유에서 떼어 다른
  실행 주체가 찾거나 회수할 수 있게 한다.
- `reclaim`: abandoned page/segment를 heap 또는 theap이 다시 소유하고 allocation에
  사용한다.
- `page free`: allocator page를 상위 segment/arena에 돌려준다. 아직 Linux RSS 반환과
  동일하지 않다.
- `purge/decommit`: 비어 있는 OS-backed 범위를 커널이 재사용하도록 한다.

따라서 `free()` 호출 직후 RSS가 줄지 않는 것은 정상일 수 있다. 반대로 RSS가 줄었다고
가상 주소 reservation까지 사라졌다고 볼 수도 없다.

## 4. Linux에서 `malloc/free`가 실제로 흐르는 길

### 4.1 공통 시작 경로

1. 실행 시 `LD_PRELOAD=/.../libmimalloc.so`가 설정되면 dynamic loader가 glibc보다
   mimalloc의 `malloc/free` symbol을 먼저 선택한다. 이 저장소는 `/proc/<pid>/maps`,
   `dlsym(mi_version)`, library SHA-256으로 이를 검증한다.
2. 대부분의 작은 `malloc`은 현재 thread의 heap/theap가 가진 allocator page의
   free list에서 block 하나를 꺼낸다. 이 fast path에는 보통 syscall이 없다.
3. 맞는 free block이 없으면 mimalloc이 다른 allocator page나 더 큰 관리 단위를 찾는다.
   그것도 없을 때 arena/segment를 확장하고 최종적으로 Linux `mmap`을 호출한다.
4. Linux overcommit에서는 두 버전 모두 일반적으로
   `MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE` 계열 mapping으로 가상 주소를 먼저
   얻을 수 있다.
5. 프로그램이 반환 pointer를 실제로 touch하면 아직 backing되지 않은 Linux page에
   minor fault가 나고 커널이 zero-filled page를 붙인다. 이때 RSS가 증가한다.
6. `free()`는 우선 mimalloc의 free list와 사용 count를 갱신한다. OS 반환은 allocator
   page가 비고 retire/purge 조건까지 충족된 뒤 별도로 일어난다.
7. 기본 decommit purge는 Linux에서 주로 `MADV_DONTNEED`를 사용한다. 주소는 남지만
   RSS가 감소할 수 있고, 이후 재사용 시 다시 minor fault와 zero-fill 비용이 생길 수 있다.

### 4.2 local free와 remote free

```text
local free                              remote free
같은 thread                             다른 thread
    │                                      │
    ▼                                      ▼
소유 page 확인                          pointer로 page metadata 확인
    │                                      │
일반 free list 갱신                     atomic xthread/thread-free list에 연결
    │                                      │
page가 비면 retire/free                  cache line이 core 사이를 이동할 수 있음
                                           │
                                   소유자 또는 reclaim 경로가 collect
                                           │
                                   page 상태를 다시 계산해 재사용/free
```

remote free는 “다른 thread가 `free()`를 호출했다”는 사실만으로 매번 syscall을 만들지는
않는다. 주 비용은 atomic 갱신, cache coherence, 나중의 list collect와 page 소유권
조정이다. 이 저장소의 `remote_free`에는 pointer 전달용 bounded queue 비용도 있으므로
`queue_only` control과 함께 읽어야 한다.

### 4.3 `madvise` 두 가지 목적

```text
빈 backing 반환 요청                    THP backing 요청
MADV_DONTNEED                            MADV_HUGEPAGE
    │                                        │
RSS 감소 가능                           적합한 정렬·크기의 mapping
재접근 fault 가능                       커널 정책이 허용하면 THP 가능
```

동일 process에서 두 호출이 모두 나올 수 있다. `strace -c`의 `madvise` 총횟수만으로
purge가 많았는지 THP hint가 많았는지 분리할 수 없다. 주소·길이·advice argument를
포함한 trace나 allocator diagnostic을 함께 봐야 한다.

## 5. mimalloc v2.1.2

### 5.1 할당 흐름

```text
malloc
  ▼
현재 thread-local heap의 size-class page
  ├─ free block 있음 ──▶ block 반환
  └─ 부족
       ▼
  segment에서 맞는 page/span 또는 abandoned segment 탐색
       ├─ 재사용 가능 ──▶ heap으로 reclaim
       └─ 부족
            ▼
       arena 또는 Linux mmap으로 새 segment 확보
            ▼
       첫 touch에서 Linux backing/RSS 발생
```

v2의 중심은 thread-local `mi_heap_t`, allocator page, 여러 page를 담는 segment다.
arena를 통해 예약된 공간을 받을 수도 있지만, abandoned memory의 전역 추적 단위는
주로 segment다.

### 5.2 retire

size class에 allocator page가 하나만 남았고 그 page가 완전히 비면 v2는 이를 바로
없애지 않을 수 있다. 작은 객체 page에는 기본 16 retire cycle에 1을 더한 만료 count를
설정하고, 이후 collect cycle에서 감소시킨다. 가까운 미래의 같은 크기 allocation이
새 page를 다시 준비하는 비용을 줄이려는 정책이다.

이 “마지막 빈 page”는 live memory는 아니지만 purge 전까지 retention에 기여할 수 있다.
retire cycle은 밀리초 단위 timer가 아니라 allocator collect가 진행될 때 감소하는
논리 cycle이다.

### 5.3 thread 종료, abandon, reclaim

일반적인 small/medium page에 사용 중 block이 남은 채 소유 thread가 종료되면 v2는
page를 abandon한다. segment의 모든 사용 page가 abandoned가 되면 segment가 전역
abandoned segment list로 이동한다. 다른 thread가 새 page를 필요로 할 때 이 list를
탐색하고 적합한 page를 자신의 heap으로 reclaim한다.

기본 `max_segment_reclaim=8`이므로 한 allocation 시도에서 abandoned segment 후보를
최대 8개 확인해 탐색 지연을 제한한다. 적합하지 않은 후보는 visited list로 옮겼다가
나중에 다시 본다. 세 번째 이후 방문에는 queue가 끝없이 길어지지 않도록 reclaim하는
경로도 있다.

```text
소유 thread 종료
  ▼
live block이 남은 page abandon
  ▼
segment의 사용 page가 모두 abandoned?
  ├─ 아니오: 기존 segment 내부 상태로 유지
  └─ 예: 전역 abandoned segment list
             │
다른 thread가 새 page 필요
             ▼
최대 8개 후보 탐색
  ├─ 적합: heap으로 reclaim하여 재사용
  ├─ 완전히 빔: segment free/purge 후보
  └─ 부적합: visited list로 이동
```

따라서 “v2는 thread가 끝나면 메모리를 영구 방치한다”는 해석은 틀리다. v2도 allocation
시점과 collect 시점에 abandoned memory를 회수한다. huge allocation은 일반
small/medium 흐름과 다르게 어느 thread든 해제할 수 있도록 즉시 abandoned로 다루는
예외가 있다.

### 5.4 purge와 THP

고정 소스의 upstream 기본값은 다음과 같다.

| 옵션 | 기본값 | 의미 |
|---|---:|---|
| `purge_delay` | 10 ms | 일반 delayed purge 대기 |
| `arena_purge_mult` | 10 | arena purge delay 배수 |
| `allow_large_os_pages` | 0 | 명시적으로 켜지 않으면 large-OS-page 요청 안 함 |

따라서 arena에 속한 빈 범위는 대략 `purge_delay × arena_purge_mult` 정책의 영향을
받아 일반 segment와 반환 시점이 같지 않을 수 있다. 정확한 purge 시점은 collect
호출과 추가 연장 조건에도 좌우된다.

Linux의 regular mapping에서 v2가 `MADV_HUGEPAGE`를 호출하는 경로는 large OS page
사용 요청이 활성화되고 mapping의 크기·정렬 조건이 맞는 경우다. 이것은 THP를
**요청하는 hint**이며 실제 THP backing을 보장하지 않는다.

## 6. mimalloc v3.4.3

### 6.1 할당 흐름

```text
malloc
  ▼
현재 thread-local theap의 size-class page
  ├─ free block 있음 ──▶ block 반환
  └─ 부족
       ▼
  arena의 size-class abandoned bitmap에서 맞는 page 탐색
       ├─ 발견 ──▶ bitmap claim 후 theap으로 reclaim
       └─ 없음
            ▼
       arena slice/page map에서 새 allocator page 구성
            └─ arena 부족 시 Linux mmap으로 arena 확장
```

v3의 `theap`은 thread-local allocation 주체다. page metadata를 객체 영역과 분리하고,
arena의 slice 및 page map/bitmap으로 free·committed·abandoned 상태를 추적한다.

### 6.2 full page도 공유를 위해 abandon

v2와 가장 중요한 차이는 abandon이 thread 종료에만 묶이지 않는다는 점이다. v3은
일반 allocation 중 small size class의 full page를 확인할 때 기본적으로 size class당
앞의 2개(`page_full_retain=2`)를 theap 쪽 탐색 후보로 유지한다. 그보다 많은 full
page는 보통 현재 theap에서 떼어 abandon한다.

full page는 당장은 빈 block이 없으므로 abandoned bitmap에 allocation 후보로 즉시
표시되지 않을 수 있다. 이후 remote free로 충분한 block이 생기면 size-class별
`pages_abandoned[bin]` bitmap에 등록되어 다른 theap의 새 allocation이 찾을 수 있다.
thread 종료 시 남은 page를 abandon하는 경로도 여전히 존재한다.

```text
small size class 탐색
  ▼
full page 발견
  ├─ 앞의 2개: theap 쪽에 우선 유지
  └─ 그 이상: page abandon
                  │
                  ├─ 여전히 full/거의 full: 무소유 상태
                  └─ remote free로 여유 발생
                           ▼
                  arena size-class abandoned bitmap
                           ▼
                  allocation 시 claim/reclaim
```

### 6.3 abandoned page의 remote free

v3에서 abandoned page의 remote free는 atomic thread-free list를 collect한 뒤 다음
세 경로를 시도한다.

```text
abandoned page에서 remote free
  ▼
atomic free list collect, used count 갱신
  ├─ 모든 block이 비었음
  │      └─▶ 즉시 allocator page free
  ├─ reclaim 조건 충족
  │      └─▶ 현재 또는 원래 theap으로 reclaim
  └─ 아직 많이 사용 중/조건 불충족
         ├─ 7/8 미만 사용으로 충분히 여유: abandoned bitmap에 재등록
         └─ 그 외: 무소유 abandoned 상태 유지
```

`page_reclaim_on_free=0`은 reclaim을 완전히 끄는 값이 아니다. 기본값 0은 해당 page가
연결되어 있던 **원래 theap**으로의 reclaim을 허용하고, 값 1은 조건을 만족하는
cross-theap reclaim까지 허용한다. -1이 완전 비활성화 값이다.

reclaim은 atomic free를 줄여 빠를 수 있지만 한 theap이 많은 page를 소유하면
thread 사이 재사용과 RSS에 불리할 수 있다. 그래서 v3는 thread-pool 여부를 감지해
원래 theap reclaim에도 더 보수적인 cross-thread 상한을 적용하고, cross-theap
reclaim도 page 수와 사용률로 제한한다.

이 고정 소스에서 `page_cross_thread_max_reclaim`의 **실제 구현 기본값은 32**다
(`src/options.c`의 `MI_DEFAULT_PAGE_CROSS_THREAD_MAX_RECLAIM`). 공개 헤더
`include/mimalloc.h`의 주석은 16이라고 적혀 있어 불일치한다. 이 문서는 실행되는
`options.c`의 32를 기준으로 한다.

### 6.4 purge와 THP

| 옵션 | Linux 기본값 | 의미 |
|---|---:|---|
| `purge_delay` | 1000 ms | 빈 범위를 재사용 후보로 오래 유지 |
| `arena_purge_mult` | 1 | arena purge delay 배수 |
| `page_full_retain` | 2 | small size class마다 우선 유지할 full page 수 |
| `page_reclaim_on_free` | 0 | 원래 theap으로 reclaim 허용 |
| `page_cross_thread_max_reclaim` | 32 | 구현 기준 cross-thread 소유 상한 |
| `allow_thp` | 1 | Android가 아닌 기본 build에서 THP 허용·적합 mapping에 hint |

v3의 기본 purge delay는 v2보다 길다. 따라서 빈 공간을 1초 정도 빠른 재사용 후보로
유지할 수 있지만 이것만으로 leak이라고 할 수 없다. v2의 arena multiplier는 10이고
v3는 1이므로 `purge_delay` 숫자 하나만 떼어 모든 범위의 반환 시점을 비교해서도 안
된다.

v3에는 `allow_thp`가 별도 옵션으로 있다. Linux에서 THP가 허용되고 mapping의
크기·정렬이 맞으면 regular mapping에 `MADV_HUGEPAGE`를 요청할 수 있다. 값 0이면
가능한 플랫폼에서 process 단위 THP disable도 시도한다. host가 `THP=never`이면
allocator hint만으로 실제 THP가 생기지는 않는다.

v3은 최소 purge 크기를 두어 arena bitmap의 너무 작은 조각 purge를 합칠 수 있다.
사용자가 `minimal_purge_size`를 지정하면 그 크기를 쓰고, 자동으로 THP large-page
크기를 쓰는 경로는 이 버전에서 THP가 탐지되고 `allow_thp=2`일 때다. 기본
`allow_thp=1`을 무조건 2 MiB purge라고 해석하면 안 된다. 이 장치는 THP backing을
잘게 쪼개는 것을 피할 수 있는 대신, purge가 늦어져 RSS가 더 오래 남거나 한 번의
kernel 작업이 커지는 trade-off를 만들 수 있다.

## 7. v2와 v3 비교

| 항목 | v2.1.2 | v3.4.3 |
|---|---|---|
| 메모리 확보·추적 중심 | allocator page를 담는 segment, 전역 abandoned segment list | arena slice, 분리 metadata, page map과 size-class abandoned bitmap |
| thread-local 주체 | heap | theap |
| full page 처리 | 보통 소유 heap의 full queue; abandon은 주로 thread 종료 시 | small size class에서 2개 우선 유지 후 일반 실행 중에도 공유를 위해 abandon |
| abandon 발생 | live block을 남긴 thread 종료가 대표적; huge는 예외 | thread 종료와 일반 full-page 전환 모두 |
| abandoned 추적 | segment 단위 global/visited list | arena의 size-class별 page bitmap과 무소유 page 상태 |
| reclaim 시점 | 새 segment/page가 필요할 때 기본 최대 8개 segment 후보 탐색 | allocation이 bitmap에서 찾을 때, 또는 remote free에서 조건부 reclaim |
| 기본 purge | 10 ms, arena multiplier 10 | 1000 ms, arena multiplier 1 |
| THP 요청 | large-OS-page 요청과 크기·정렬 조건을 만족하는 조건부 hint | 별도 `allow_thp=1` 기본 옵션과 적합 mapping의 hint |
| 예상 trade-off | 빠른 일반 purge로 RSS 반환이 빠를 수 있으나 fault/재준비 증가 가능 | 더 긴 재사용 window와 page 공유가 유리할 수 있으나 workload에 따라 RSS·atomic·system CPU 비용 가능 |

이 표는 구조로부터 예상할 수 있는 방향이지 성능 결과가 아니다. object size, 수명,
touch, producer/consumer 비대칭, CPU topology, THP와 purge 정책이 실제 결과를
바꾼다.

## 8. 고정 `io_context` worker 프로그램에 적용해 읽기

수백 일 유지되는 고정 worker에서는 thread 종료가 드물다. 따라서 v2의 대표적인
“thread 종료→abandon” 경로는 thread churn 프로그램보다 덜 직접적일 수 있다.
반면 worker 사이에서 task나 buffer 소유권이 자주 이동하면 두 버전 모두 remote-free
atomic 경로를 계속 사용한다. v3에서는 여기에 일반 full-page abandon, abandoned
bitmap 등록, remote-free reclaim/re-abandon이 더 직접적으로 관여할 수 있다.

그렇다고 관측 차이를 곧바로 “abandon 때문”이라고 부를 수는 없다. RSS가 높을 때는
최소한 다음 원인을 나눠 확인한다.

| 가능한 원인 | 뜻 | 확인할 지표·진단 |
|---|---|---|
| live working set | 아직 실제 객체가 살아 있음 | outstanding pointer/bytes, workload phase, allocation/free count |
| retired empty page | 빈 page를 재사용 목적으로 잠시 보유 | mimalloc verbose/stats의 retire·page count, collect 전후 |
| abandoned page | 소유 theap/heap에서 떨어졌지만 live block이 남음 | mimalloc abandoned/reclaim 통계, thread 종료와 remote-free phase |
| purge 대기 | page는 비었으나 delay가 만료되지 않음 | `MIMALLOC_PURGE_DELAY`, 시간별 RSS, idle 뒤 RSS, `madvise` trace |
| arena reservation | 큰 주소 범위를 계속 예약 | `/proc/<pid>/maps`, `VmSize`와 RSS 차이 |
| THP backing | anonymous 범위 일부가 huge page로 resident | `smaps_rollup`의 `AnonHugePages`, `THPeligible`, `/proc/vmstat`의 `thp_*` delta |

## 9. r19–r21 실측을 이 용어로 해석하기

이 절은 이미 실행한 좁은 진단의 관측만 요약한다. 내부 원인의 확정 증명은 아니다.

- r19의 `large_alloc/per-page-touch`, host `THP=madvise` 조건에서 v3.4.3은 두 policy
  arm 모두 `madvise` 중앙값 748회와 최대 `AnonHugePages` 약 86 MiB를 보였다.
  v2 upstream-default는 각각 30회와 0 B, v2 native request는 2회와 약 84 MiB였다.
  이 결과는 v3의 `allow_thp`/mapping hint와 purge 활동이 기여했을 가능성과
  양립하지만, `strace -c` 총횟수만으로 각 `madvise`의 목적을 확정하지 못한다.
- r20의 4 producer+4 consumer 고정-worker native-request 실험에서 v3/v2 처리량
  중앙 비율은 fixed-small 1.019, mixed-wide 1.012였다. mixed-wide 관측 종료 RSS는
  1.130, system CPU는 2.125였지만 RSS는 종료 후 단발 관측이며 처리량 반복 범위도
  넓었다. 이를 abandon이나 retention의 확정 효과로 부르지 않는다.
- r21에서 두 버전의 purge delay를 1000 ms로 맞춘 mixed-wide 실험은 최대 sampled
  RSS v3/v2 0.597, 최대 `AnonHugePages` v3/v2 97.0, system CPU v3/v2 2.548을
  보였다. 기본 purge 정책이 r20 RSS 비교의 큰 교란 변수였다는 근거지만, 낮은
  RSS·높은 THP·높은 system CPU 사이의 인과 경로까지 증명하지는 않는다.

따라서 운영 canary에서는 같은 purge 정책 아래 RSS time series, cgroup peak,
`AnonHugePages`, minor fault, `madvise` argument별 호출률, p99/p99.9 latency와
CPU/request를 함께 수집해야 한다.

## 10. 흔한 오해

- `free()`는 곧 `munmap()`이 아니다.
- allocator page는 Linux 4 KiB page가 아니다.
- 큰 `VmSize`는 큰 RSS나 memory leak의 증거가 아니다.
- RSS가 즉시 줄지 않는 것은 그 자체로 leak이 아니다.
- `AnonHugePages`는 THP 지표이지 HugeTLB 사용 증거가 아니다.
- `MADV_HUGEPAGE`는 요청이지 실제 huge-page 배정 보장이 아니다.
- `madvise` 호출 수만으로 purge와 THP hint를 구분할 수 없다.
- v2도 abandoned memory를 reclaim한다.
- v3의 `page_reclaim_on_free=0`은 reclaim 완전 비활성화가 아니다.
- upstream-default 비교와 purge/THP를 맞춘 normalized-policy 비교는 서로 다른
  질문에 답한다.

## 11. 소스 확인 지점과 관련 문서

기본값과 흐름은 고정 source tree의 다음 파일에서 확인했다.

- v2: `src/options.c`, `src/page.c`, `src/segment.c`, `src/prim/unix/prim.c`
- v3: `src/options.c`, `src/page.c`, `src/free.c`, `src/arena.c`, `src/os.c`,
  `src/prim/unix/prim.c`, `include/mimalloc.h`
- source 고정 정보: `manifests/sources.lock`

실측 세부 조건과 한계는 다음 문서를 따른다.

- [r19 syscall·large-page 진단](diagnostic-r19-report.ko.md)
- [r20 native-request 고정-worker 보고서](native-persistent-r20-report.ko.md)
- [r21 purge-delay 일치 RSS 검증](purge-matched-r21-report.ko.md)
- [상세 실험 보고서](experiment-report.md)
