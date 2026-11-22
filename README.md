# mimalloc의 처리 비용과 메모리 흐름 이해하기

## 2026-11-22 dev3와 v3.7.0 비교

dev3 `15d1247d`와 v3.7.0에서 보안 모드와 내부 large page를 교차해 본 측정 120회를 수행했습니다.
dev3의 보안 ON에서 256 KiB 객체를 스레드 간에 인계할 때 내부 large page를 켜면 처리량이
10.33에서 167.78 GiB/s로, 해제 1초 뒤 RSS가 22.7에서 179.5 MiB로 증가했습니다.
별도 시스템 호출 계수로 singleton guard의 비용을 확인했고, 4 KiB 원격 해제는 프로세스 THP 옵션을 바꿔 비교했습니다.
[측정 보고서](docs/dev3-20261122-report.md) · [원인 분석](docs/dev3-20261122-mechanisms.md) · [전체 결과표](experiments/dev3-20261122-v1/tables.md)

## 앞선 성능 실험

[v3.7.0 large page ON A/B](docs/v370-large-pages-report.md).
256 KiB 처리량은 기본 대비66.5% 증가해 v3.6.1 수준으로 회복했고 RSS는38.6% 감소했습니다.
64 KiB는6.5% 느려졌고, 4·16 KiB 저하는 해결되지 않았습니다. 별도 새 빌드·36회 측정입니다.

[v3.7.0을 추가한 여섯 릴리스 비교](docs/v370-report.md).
기존 결과를 보존하고 새 빌드·동결 계획으로 458개 기록을 검증했습니다.
v3.6.1 대비 기본 4 KiB·2쌍 처리량은 약 4.7–6.8% 낮았고,
별도 동일 바이트 비교의 256 KiB에서는 약 39.6% 낮았습니다.
purge delay10/mult1의 RSS는 낮았지만 작업 중 생존량도 달랐습니다.
각 조건 3회의 탐색 관찰이며, 모든 조건의 개선이나 특정 수정의 단독 효과를 뜻하지 않습니다.
[계획](docs/v370-plan.md) · [소스 변경점](docs/v370-source-notes.md) ·
[코드 분석](docs/v370-code-analysis.md) · [재현](observation/RELEASE_V370.md).
현재 식별자는 `release-v370-v1`, `purge-delay-v370-v1`, `allocation-size-v370-v1`입니다.

앞선 후속: [dev3 보안 모드 성능·메모리 비용](docs/security-20261106-report.md).
OFF/MINIMAL/CHECKED/ON/FULL과 CHECKED+PAC=WEAK를 비교했습니다.
ON은 조건별 약 2.0–3.3배, FULL은 약 3.4–20.2배 시간이 필요했습니다.
CHECKED 비용은 객체 크기와 해제 방식에 따라 크게 달랐습니다.
[전체 수치](docs/security-20261106/tables.md) · [재현](observation/SECURITY_20261106.md).
당시 후속 식별자는 `security-20261106-v1`이며 기존 결과는 보존합니다.

앞선 후속: [dev3 d6716d33과 v3.6.1 직접 측정](docs/dev3-20261106-report.md).
일반 Release의 remote-free·메모리 수명·스레드 생성/종료를 조건당 5회 비교하고
178개 raw 기록을 검증했습니다. 1 KiB에서 개선 신호는 있었지만 반복별 방향이 달랐고,
전체적인 성능·메모리 반환 개선은 확인하지 못했습니다.
[전체 수치](docs/dev3-20261106/tables.md) · [재현](observation/DEV3_20261106.md).
당시 후속 식별자는 `dev3-20261106-v1`이며 기존 동결 결과는 보존합니다.

앞선 후속: [v3.6.1을 추가한 다섯 버전 비교](docs/v361-report.md).
기본 동작·purge 대기시간·할당 크기를 새 namespace에서 비교했고 총 379개 실행을 검증했습니다.
v3.6.0 대비 기본 1 KiB·2쌍 처리량은 약 14%, 4 KiB 조건은 약 4–6% 낮았습니다.
16–256 KiB의 동일 바이트 비교에서는 차이가 작았으며, 각 조건 3회 탐색 관찰입니다.
[계획](docs/v361-plan.md) · [소스 변경점](docs/v361-source-notes.md) · [재현](observation/RELEASE_V361.md).
당시 식별자는 `release-v361-v1`이며 `purge-delay-v361-v1`, `allocation-size-v361-v1`을 포함합니다.

앞선 후속: [할당 크기 4/16/64/256 KiB 비교](docs/allocation-size-report.md).
총 처리 바이트·128 MiB 상한·256 KiB 인계 배치를 고정해 네 버전을 48회 관찰했습니다.
v3.6.0은 4→16/64 KiB에서 바이트 처리량이 약 3.1/3.5배 높아졌고,
256 KiB의 추가 이득은 확실하지 않았습니다. 당시 식별자는 `allocation-size-v1`입니다.

앞선 후속: [purge 대기시간을 맞춘 RSS 비교](docs/purge-delay-report.md).
네 버전에서 delay 10/1,000 ms와 arena 배수 1을 맞춰 24회 관찰했습니다.
v3의 반환 주기는 정렬되지만 RSS 높이는 달랐고, v2는 약 132 MiB를 유지했습니다.
후속 식별자는 `purge-delay-v1`입니다.

2026-10-24에 **v3.6.0을 추가해 네 버전을 다시 비교**했습니다.
이 비교의 식별자는 `release-v360-v1`입니다.

[v3.6.0 결과와 해석](docs/v360-report.md) · [계획](docs/v360-plan.md) ·
[전체 수치](docs/v360/tables.md) · [재현 절차](observation/RELEASE_V360.md)

v3.5.3 대비 1 KiB 동시 처리량은 1쌍 약 16%, 2쌍 약 34% 회복했습니다.
2쌍에서는 idle RSS도 약 68→138 MiB로 커졌습니다. 64 B와 4 KiB의 처리량은
반복 범위가 겹쳤고, 4 KiB에서 v3.5.0 대비 낮은 처리량은 남았습니다.
새 free_count를 포함한 스레드 통계 귀속도 기존과 같았습니다.

## 앞선 동시 처리 관찰

동시 할당·원격 해제에서 **v2.1.2/v3.5.0/v3.5.3**의 객체 크기(64 B–4 KiB),
작업자 쌍(1/2), 생존 요청량 상한(128/512 MiB)을 비교했습니다.
본 관찰 90회와 별도 고정 버퍼 대조 30회를 완료했습니다.

[동시 처리 결과와 해석](docs/concurrency-report.md) · [동결 계획](docs/concurrency-plan.md) · [실행 절차](observation/CONCURRENCY.md)

3.5.3은 64 B에서 3.5.0보다 처리량이 높았지만, 4 KiB에서는 낮았습니다.
512 MiB 상한에서도 방향은 같았습니다. 실제 생존량이 상한보다 작아지는 패턴과,
v2의 큰 메모리 보유량 및 v3의 작업 중 반환을 함께 확인했습니다.

이 관찰의 식별자는 `concurrency-v1`입니다. 정확한 값과 적용 범위는 보고서를 참고하세요.

추가 진단: [v3.5.3 스레드별 통계 재현](docs/thread-stats-report.md).
지연 갱신·병합 때문에 스레드 조회값이 실제 생존량과 어긋나는 현상을 확인했고,
작은 테스트 범위의 최종 heap 집계는 정확했습니다.
[A 할당 전담/B 해제 전담 후속 확인](docs/thread-stats-ab-report.md)에서는
전체 합계와 별개로 해제량의 스레드 귀속이 실제 호출 실적과 달라지는 것을 확인했습니다.

## 앞선 순차 관찰

새 프로그램으로 4 KiB 객체 32,768개(128 MiB)의 할당·쓰기·일부 해제·전체 해제·
30초 휴식·재사용을 관찰했습니다. v2.1.2/v3.5.0/v3.5.3에서 해제 담당자만 A/B로
바꾼 18개 흐름과, 명시적 수집을 추가한 별도 6개 진단을 완료했습니다.

[결과와 해석](docs/memory-behavior-report.md) · [계획](docs/memory-behavior-plan.md) · [실행 절차](observation/README.md)

이번 관찰에서는 객체를 모두 해제해도 RSS가 유지됐습니다. 다음 사용에서의
메모리 증가와 명시적 수집의 효과는 버전마다 달랐습니다. 해제·재사용 준비·
OS 반환을 나눠 보는 것이 핵심입니다. 작은 시간 차이의 우열은 확정하지 않았습니다.

Execution status: Complete

앞선 식별자는 `memory-behavior-v1`입니다. 동결 plan.json은 측정 당시 값으로
보존하고 완료 상태는 experiments/memory-behavior-v1/status.json에 기록합니다.
기존 작업의 계획·하네스·결론은 폐기했고 새 관찰에서 사용하지 않았습니다.
[폐기 기록](legacy/retired-2026-09-21/README.md)은 복구용입니다.
