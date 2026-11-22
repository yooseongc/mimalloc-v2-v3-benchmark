# perf 접근 검증

2026-11-01. 실제 테스트 완료. 기존 profiling 진단의 실패 기록은 보존한다.

기본 Docker 컨테이너에서 task-clock/cycles 모두 permission 오류였다.
호스트 perf_event_paranoid=2, kptr_restrict=1이며 변경하지 않았다.
Docker 20.10.23 환경은 --cap-add PERFMON을 unknown capability로 거부했다.
임시 컨테이너에 --security-opt seccomp=unconfined를 주고 사용자 공간 이벤트(:u)를
사용하자 추가 capability/privileged 없이 계측에 성공했다.
이 옵션은 해당 컨테이너의 syscall 필터 전체를 해제하므로 신뢰하는 로컬 진단 실행에
한정한다. 호스트나 일반 컨테이너의 설정을 변경한 것은 아니다.

실제 검증: task-clock:u, cycles:u, instructions:u 성공. cycles:u 99 Hz 및
DWARF call graph 수집 57 samples, lost 0, perf report 함수/호출 경로 출력 성공.
검증 workload는 Python 정수 연산이며 mimalloc 성능 원인 분석 결과는 아니다.
커널 이벤트, 전체 시스템 profiling, 모든 하드웨어 이벤트 지원은 검증하지 않았다.

```powershell
docker run --rm --pull=never --network none --security-opt seccomp=unconfined --cpuset-cpus=0,2,4,6,8,10 --mount "type=bind,source=C:\Users\user\workspace\mimalloc-test,target=/work" --workdir /work sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877 python3 observation/probe_perf_access.py
```

스크립트는 기존 결과를 덮어쓰지 않도록 experiments/perf-access-v1이 존재하면 거부한다.
재시험은 새 출력 경로를 사용한다. 원자료: experiments/perf-access-v1/result.json,
perf.data, probe-*.stdout/stderr. 앞선 inline shell probe는 셸 확장 때문에 CPU loop가
실행되지 않았으므로 샘플링 검증 근거에서 제외하고 위 Python workload로 재검증했다.

후속 benchmark에서도 일반 OFF 측정과 perf 진단 실행을 분리한다. perf 실행에는
사용자 공간 이벤트와 위 임시 옵션을 명시해야 한다.
