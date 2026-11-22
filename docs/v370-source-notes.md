# v3.6.1 → v3.7.0 소스 사전 점검

2026-11-18. 공식 태그 v3.7.0의 peeled commit은
`1ed67b5156a763441d2ec3c20221a7b3cd866129`, annotated tag object는
`7d589caad1c331b677719adb3c8f082c15400f3d`다. git ls-remote와 새 checkout으로 확인했다.
소스는 extern/mimalloc-v3.7.0에 별도 보존하고 수정하지 않는다.

공식 [변경 기록](https://github.com/microsoft/mimalloc/blob/v3.7.0/readme.md#releases)은
2026-11-16 릴리스로 표시한다. MTE/PAC, 보안 환경, realloc 메모리 절약,
arena purge 누락 수정, 성능 개선, CPython 통합 및 플랫폼 수정을 기술한다.
이 설명은 upstream 주장이고 이번 측정 결과가 아니다.

| 옵션 | v3.6.1 | v3.7.0 | 취급 |
|---|---:|---:|---|
| purge_delay | 1000 ms | 1000 ms | 기본 비교는 유지; 별도 10/1000 ms |
| arena_purge_mult | 4 | 4 | 별도 purge/크기 비교에서 1 |
| page_reclaim_on_free | 0 | 0 | 기본 유지 |
| stats_merge_on_collect | 1 | 1 | API 진단에서 0/1 |
| stats_merge_threshold | 4 MiB | 4 MiB | API 진단에서 getter 검증 |

근거: 각 checkout의 src/util/options.c와 CMakeLists.txt. v3.7.0의
MI_SECURE는 DEFAULT/OFF/MINIMAL/CHECKED/ON/FULL이며 공통 빌드는 OFF를 명시한다.
MI_MTE 기본은 OFF, MI_PAC의 DEFAULT는 MTE가 꺼진 이 환경에서 OFF로 해석된다.
캐시와 실제 컴파일 플래그를 빌드 증거로 보존한다.

기존 realloc-20261110-v1은 개발 커밋 사이의 원인 분리 진단이다. 이번 공식 릴리스
malloc/free 비교의 표본과 합치지 않는다. 재할당 단계(reallocate)는 free 후 새 malloc이며
realloc API 자체의 성능 검증이 아니다. 하드웨어 MTE/PAC, 보안 방어 효과,
CPython/Rust/macOS의 기능 개선을 이번 Linux x86-64 관찰로 검증했다고 주장하지 않는다.
