# r29 측정 후 하네스·해석 감사

작성일: 2026-09-21. 사용자 요청으로 소스, 실제 측정 바이너리의 역어셈블,
630개 원시 레코드 및 분석 코드를 다시 점검했다. 동결 계약·측정 바이너리·
원시 결과·제외 기준은 변경하지 않았다. 아래는 측정 후 발견과 해석 정정이다.

## 판단

실행 성공과 allocator 비교의 타당성은 별개다. 630건의 valid 상태는 당시
검증 규칙을 통과했다는 뜻이다. 하네스가 의도한 일을 모두 수행하거나,
allocator 차이를 충분히 분리해 측정했다는 보증으로 사용할 수 없다.
이전에 제시한 p99 수치를 allocator 호출 성능 개선의 근거로 사용하면 안 된다.

## 확인된 문제

1. **지연시간의 측정 대상이 오해되기 쉽다.**
   `tcp_policy_record.cpp:333–337`에서 malloc과 ingress 작업이 끝난 다음
   표본 시각을 기록한다. `:417–420`에서 표본을 기록한 다음 free한다.
   따라서 p99는 개별 malloc/free 호출 시간이 아니라 할당 후부터 해제 직전까지의
   큐 이동·대기·bank 보관·중간 처리 시간이다. 다른 객체의 해제 비용이나
   allocator 속도 변화는 큐 상태를 통해 간접적으로 영향을 줄 수 있다.
   할당이 느려져 유입이 줄어도 큐 지연이 줄어들 수 있으므로 p99 감소만으로
   allocator 개선을 판단할 수 없다. 이번 감소의 원인이 그것이라고 확정한 것은 아니다.

2. **서비스 record 계산의 최적화 방지에 결함이 있다.**
   `record_work`는 지역 변수 `record_checksum`만 변경하며, worker 끝에서는
   `(void)record_checksum`으로 버린다 (`tcp_policy_record.cpp:192–199,402,412,455`).
   출력되는 `stats.checksum_record`는 별개의 sequence 합이다. 기존 correctness 검사는
   payload 계산이 실제 수행되었는지를 검증하지 않는다.
   측정 바이너리 SHA-256 `cae35ae342d94552be35fec06de5f46a7a108496dbb59debc18f6c201aa6528b`
   의 record worker (`0x40bef0`, lambda #5)를 역어셈블해 확인했다.
   record payload의 mix 루프가 없고, mix 상수나 해당 함수를 호출하는 경로도 없다.
   따라서 서비스 모드 결과를 의도했던 전체 서비스 처리의 재현으로 사용하지 않는다.
   ingress/policy/return 등 다른 작업까지 모두 제거됐다는 뜻은 아니다.

3. **Remote-free 하네스의 측정·동기화 비용이 크다.**
   `remote_free.cpp:94–96`은 모든 객체에 대해 시계를 두 번 읽고 공유 atomic을
   갱신한다. 큐가 가득 차지 않아도 측정하므로 `backpressure_ns`에는 enqueue 자체의
   비용도 들어간다. `:107–109`의 checksum/consumed와 대기 카운터도 공유 atomic이다.
   `:61`의 enqueue/dequeue 위치는 cache line 분리 선언 없이 나란히 있다.
   이 구조는 AGENTS의 thread-local 통계와 queue head/tail 분리 요구를 충족하지 않는다.
   Queue-only 중앙값은 5.20–6.43 M transfers/s, remote 결과는 약 5 M allocations/s로
   같은 규모다. 큐 병목 가능성을 지지하지만 비용 비중이나 원인을 정량 확정하지는 않는다.
   Queue-only는 각 버전 3회이며 별도 시점에 실행되어, 정밀한 비용 차감용 대조군이 아니다.

4. **Local 결과에도 정상상태 측정의 한계가 있다.**
   core warm-up은 0이다. `main.cpp:119–169`에서 시작 신호 후 vector 준비,
   size 계산, 해제 순서 생성 등을 수행하며 종료 시간은 worker join 이후다.
   thread 종료에 따른 allocator 정리 비용도 포함될 수 있다. 이들은 allocator 호출 외
   비용을 섞지만, 이것만으로 관찰된 6.1% 차이가 잘못됐다고 단정할 수 없다.

5. **표와 통계의 설명을 개선해야 한다.**
   버전별 중앙값의 비율과 같은 반복끼리 구한 비율의 중앙값은 다른 추정량이다.
   service p99는 전자가 0.9260, 후자가 1.0696으로 방향도 달랐다.
   실제로 15쌍 중 v3.5.3이 짧았던 것은 7쌍이다. 독립 재계산에서도 같아
   분자·분모가 뒤바뀐 계산 오류는 확인하지 못했다. 결과를 본 후 유리한 추정량으로
   바꾸면 안 되지만, 서로 다른 추정량을 나란히 제시한 표는 설명이 부족했다.
   95% CI는 다중 비교 미보정이며 WSL2 스케줄링·host 변동·하네스 편향을
   포괄하는 오차 범위가 아니다. CI에 1이 포함된다고 동등성이 입증되는 것도 아니다.

## 유지할 수 있는 관찰

- local mixed-wide 8-worker는 원시 데이터 독립 재계산에서 비율 중앙값
  0.939498, 15쌍 중 14쌍에서 처리량 감소였다. 현재 하네스에서의 회귀 신호로
  보존하되 allocator 자체의 일반적인 6.1% 회귀로 확정하지 않는다.
- allocator 모드 pipeline의 비율 0.899650은 큐 체류 구간 p99에 대한 관찰로만
  남긴다. malloc/free 호출 p99 개선이라고 표현하지 않는다.
- remote/service의 차이 미확정은 성능 동등성의 근거가 아니다.
- memory-return 관찰은 별도 코드 경로다. 위 record 계산 결함이 그 결과를
  직접 무효화하지는 않는다. 단, 512 MiB/5초/해당 정책의 관찰 범위를 유지한다.

독립 재계산과 바이너리 확인 요약은
[post-measurement-audit.json](../experiments/r29-v353-v1/post-measurement-audit.json)에 있다.
역어셈블은 아래 명령으로 재생성할 수 있다 (고정된 r29 컨테이너 안에서 실행).

```sh
objdump -d -C build/benchmark-release/benchmark/mimalloc-bench > build/r29-audit-disassembly.txt
```

## 후속 실험에 필요한 변경

새 revision에서 record payload checksum을 worker별로 보존하고 측정 후 검증한다.
Release 바이너리에도 의도한 작업이 남는지 확인한다. Remote 통계는 worker별로
모으고 시계 조회를 표본화하며 queue head/tail을 분리한다. Local은 warm-up과
준비·종료 구간을 분리한다. 할당 호출 지연과 pipeline 체류 지연은 별도 지표로
정의하고, pipeline 비교에는 동일 유입 부하에서의 실험을 추가한다.

수정 후 correctness·smoke·pilot로 비용과 변동을 점검하고 새 설계를 동결한 뒤
local mixed-wide 8-worker, remote 대조군, pipeline부터 다시 측정해야 한다.
이번 감사에서는 재측정을 수행하지 않았다.
