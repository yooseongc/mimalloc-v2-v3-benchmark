# v3.6.0 → v3.6.1 소스 사전 점검

2026-10-31. v3.6.1 commit: 56dc5eb80145f9a3ba7ca23d47c6a248b9d8586c.
공식 태그의 소스를 별도 checkout하고 수정하지 않았다.

| 항목 | v3.6.0 | v3.6.1 | 비교에서의 취급 |
|---|---|---|---|
| page_reclaim_on_free | 1 | 0 | 기본 비교에 차이를 유지 |
| stats_merge_threshold | 512 KiB | 4 MiB | 기본값 진단에서 getter 검증, 병합 비활성 진단에서는 0 |
| stats_merge_on_collect | 1 | 1 | stats 진단에서 0/1 분리 |
| purge_delay | 1000 ms | 1000 ms | purge 후속에서 10/1000 명시 |
| arena_purge_mult | 4 | 4 | purge/크기 후속에서는 1 명시 |
| MI_SECURE | OFF | OFF, MINIMAL 선택지 추가 | 공통 OFF 빌드 |

근거는 각 태그의 src/util/options.c와 CMakeLists.txt다.
page_reclaim_on_free의 0은 모든 회수를 끄는 값이 아니다. 소스 주석상 originating
theap으로의 회수만 허용한다. 1은 다른 theap으로의 회수도 허용하고 -1은 완전 비활성이다.

v3.6.1 include/mimalloc/heap/page-map.h와 src/heap/page-map.c는 2단계 pagemap을
사용한다. 정적 process 상태가 mi_process_t로 모이는 변경도 있다. 따라서 이 릴리스의
차이를 단순 버그 수정만으로 취급하지 않는다. pagemap, 통계 병합, 회수 정책의 개별
인과 효과는 기본 버전 비교만으로 분리할 수 없다.

공식 변경 기록: https://github.com/microsoft/mimalloc/blob/v3.6.1/readme.md#releases
공식 릴리스: https://github.com/microsoft/mimalloc/releases/tag/v3.6.1

본 비교는 malloc/free와 원격 해제 관찰이다. CPython, fork, Rust, WASI,
C23 sized-free, STL allocator의 변경에 대한 기능 검증을 주장하지 않는다.
