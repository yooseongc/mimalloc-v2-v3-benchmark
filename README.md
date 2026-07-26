# mimalloc v2.1.2 vs v3.4.3 benchmark

동일한 Rocky Linux 8 컨테이너 환경에서 Microsoft mimalloc `v2.1.2`와 `v3.4.3`을 재현 가능하게 비교하는 C++17 benchmark 프로젝트입니다. 동일 스레드 churn, remote free, burst/purge, 대형 할당, 고정 worker 장기 실행 패턴을 다룹니다.

## 실행 상태와 결과

설계는 동결되었고 CPU/THP 통제 비교(r12/r13), 대형 페이지 진단(r19), 고정 worker native large-page request 비교(r20), purge delay를 맞춘 RSS/AnonHugePages 샘플링(r21)을 실행했습니다.

- [실험 설계서](docs/experiment-design.md)
- [상세 실험 보고서](docs/experiment-report.md)
- [Linux 메모리·mimalloc 한글 용어집](docs/memory-allocator-glossary.ko.md)
- [한글 HTML 보고서](docs/experiment-report.ko.html)
- [고정 worker 진단 보고서](docs/native-persistent-r20-report.ko.md)
- [purge delay 일치 RSS 검증 보고서](docs/purge-matched-r21-report.ko.md)
- [집계 결과와 그래프](results/)

원시 repetition 기록과 command log는 용량 및 호스트 정보 노출을 줄이기 위해 Git에서 제외합니다. 공개 저장소에는 재현 스크립트, 실행 manifest, 집계 결과, 보고서, 생성 그래프를 포함합니다.

## 빠른 시작

```powershell
./scripts/fetch_sources.sh
./scripts/build_mimalloc.sh
./scripts/build_benchmark.sh
./scripts/validate_environment.sh
./scripts/smoke_test.sh
```

전체 실행은 `config/`과 `manifests/`의 계획을 사용합니다. 실제 측정은 고정된 컨테이너/CPU/THP 조건에서 수행해야 하며, 상세 절차와 유효성 기준은 설계서를 따릅니다.
