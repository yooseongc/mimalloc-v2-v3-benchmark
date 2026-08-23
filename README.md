# mimalloc v2.1.2 vs v3.4.3 vs v3.5.0 benchmark

동일한 Rocky Linux 8 컨테이너 환경에서 Microsoft mimalloc `v2.1.2`, `v3.4.3`, `v3.5.0`을 재현 가능하게 비교하는 C++17 benchmark 프로젝트입니다. 동일 스레드 churn, remote free, burst/purge, 대형 할당, 고정 worker 장기 실행 패턴을 다룹니다.

## 실행 상태와 결과

설계는 동결되었고 CPU/THP 통제 비교(r12/r13), 대형 페이지 진단(r19), 고정 worker native large-page request 비교(r20), purge delay를 맞춘 RSS/AnonHugePages 샘플링(r21)을 실행했습니다.

기존 동결 결과는 `v2.1.2`/`v3.4.3` 및 별도 r23a `v3.4.3`/`v3.4.5` epoch에 해당합니다. `v3.5.0`은 r24 amendment로 추가되었고, 최종 비교는 고정된 r25 하네스로 세 버전을 모두 다시 실행했습니다. r25 core 225건, memory-return 450건, latency 90건의 유효 레코드를 확보했으며 perf counter는 커널 권한 거부로 unavailable 처리했습니다. 각 epoch의 결과는 서로 합치지 않습니다.

- [실험 설계서](docs/experiment-design.md)
- [상세 실험 보고서](docs/experiment-report.md)
- [v3.5.0 r24 3버전 비교 보고서](docs/v3.5.0-r24-report.md)
- [r25 고정 하네스 통합 비교 보고서](docs/experiment-report-r25.md)
- [Linux 메모리·mimalloc 한글 용어집](docs/memory-allocator-glossary.ko.md)
- [한글 HTML 보고서](docs/experiment-report.ko.html)
- [고정 worker 진단 보고서](docs/native-persistent-r20-report.ko.md)
- [purge delay 일치 RSS 검증 보고서](docs/purge-matched-r21-report.ko.md)
- [집계 결과와 그래프](results/)

원시 repetition 기록과 command log는 용량 및 호스트 정보 노출을 줄이기 위해 Git에서 제외합니다. 공개 저장소에는 재현 스크립트, 실행 manifest, 집계 결과, 보고서, 생성 그래프를 포함합니다.

## 현재 활성 실험

새 측정의 단일 진입점은 `experiments/ACTIVE`가 선택한
`r26-baseline-v1`입니다. r2--r25 계획과 결과는 재현성을 위해 원래
경로에 보존하지만 historical read-only로 취급하며, 활성 실행기는
그 manifest나 raw 결과를 읽지 않습니다.

고정 범위는 r25에서 검증된 Core 5개 셀, 축소된 Memory-return 6개 셀,
Tail-latency 2개 셀입니다. 실행은 기본적으로 한 번에 matched
three-version block 하나만 처리하고, 각 attempt를 원자적으로 저장한 뒤
다음 호출에서 자동 재개합니다.

```bash
# 무엇이 실행될지 확인 (기본: matched block 1개)
bash scripts/container/run_active.sh --stage smoke --profile core

# smoke와 measured 실행
bash scripts/container/run_active.sh --stage smoke --profile core --execute
bash scripts/container/run_active.sh --stage measured --profile core --execute

# 진행률 확인
bash scripts/container/run_active.sh --stage measured --profile core --status
```

계약과 전체 고정 matrix는
[`experiments/r26-baseline-v1/contract.md`](experiments/r26-baseline-v1/contract.md)와
[`experiments/r26-baseline-v1/plan.json`](experiments/r26-baseline-v1/plan.json)에
있습니다. 기존 epoch 경계는 [`legacy/README.md`](legacy/README.md)를
따릅니다.

## 빠른 시작

```powershell
./scripts/fetch_sources.sh
./scripts/build_mimalloc.sh
./scripts/build_benchmark.sh
./scripts/validate_environment.sh
./scripts/smoke_test.sh
```

전체 실행은 `config/`과 `manifests/`의 계획을 사용합니다. 실제 측정은 고정된 컨테이너/CPU/THP 조건에서 수행해야 하며, 상세 절차와 유효성 기준은 설계서를 따릅니다.
