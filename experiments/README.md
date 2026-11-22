# 현재 관찰과 폐기 범위

`ACTIVE`는 `release-v361-v1`이다. v3.6.1을 추가해 다섯 버전을 현재 환경에서
재측정했다. 기본/후속 측정과 검증 379개 실행을 완료했으며 기존 동결 자료는 보존했다.
후속 namespace는 `purge-delay-v361-v1`, `allocation-size-v361-v1`이다.
[계획](../docs/v361-plan.md) · [보고서](../docs/v361-report.md) · [재현](../observation/RELEASE_V361.md).

앞선 `allocation-size-v1`은 동일 총 바이트로 네 버전의
4/16/64/256 KiB 처리량·RSS를 관찰했다. [계획](../docs/allocation-size-plan.md),
[결과](../docs/allocation-size-report.md), [재현](../observation/ALLOCATION_SIZE.md).
앞선 [동일 purge 대기시간 관찰](../docs/purge-delay-report.md)도 별도 보존한다.

`release-v360-v1`은 v3.6.0을 추가한 네 버전의 비교이며
[계획](../docs/v360-plan.md)과 [재현 절차](../observation/RELEASE_V360.md)를 따른다.
앞선 질문 중심 관찰과 원자료는 보존하며, 새 비교는 네 버전을 다시 실행한다.
기본 관찰·검증·원인 대조를 완료했다. [v3.6.0 결과](../docs/v360-report.md).

앞선 `concurrency-v1`에서는 v2.1.2를 포함한 세 버전의 동시성·객체 크기·공간 확대
계획은 [concurrency-plan](../docs/concurrency-plan.md), 실행 절차는
[CONCURRENCY](../observation/CONCURRENCY.md)에 있다.
본 관찰 90회와 별도 retained 대조 30회를 완료했고
[결과](../docs/concurrency-report.md)에 처리량과 메모리 사용을 함께 설명했다.

앞선 `memory-behavior-v1`에서는 새 프로그램으로 기본 관찰 18개와
별도 수집 진단 6개를 완료했다. 계획은 동결됐고 완료 상태는 해당 디렉터리의
status.json, 검증 근거는 validation.json에 있다.

[결과](../docs/memory-behavior-report.md) · [계획](../docs/memory-behavior-plan.md) · [실행 절차](../observation/README.md)

이전 실험은 현재 작업에서 폐기했다. 이전 하네스·실행기·결과를 새 구현이나 분석에
사용하지 않았다. [전체 폐기 기록](../legacy/retired-2026-09-21/README.md).
