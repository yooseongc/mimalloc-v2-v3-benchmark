# v3.6.0 비교 재현

활성 계획은 [v360-plan](../docs/v360-plan.md), 식별자는 `release-v360-v1`이다.
네 버전은 v2.1.2, v3.5.0, v3.5.3, v3.6.0이며 기존 관찰 자료는 덮어쓰지 않는다.
같은 Rocky Linux 이미지에서 네 라이브러리를 새로 빌드한다. 버전별 SHA와 환경은
`experiments/release-v360-v1/lifecycle/artifacts.json`에 기록한다.

PowerShell에서 프로젝트 루트를 작업 디렉터리로 사용한다.

```powershell
$image = 'sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877'
$mount = 'type=bind,source=C:\Users\user\workspace\mimalloc-test,target=/work'
docker run --rm --pull=never --network none --cpuset-cpus=0,2,4,6,8,10 --cpuset-mems=0 --mount $mount --workdir /work $image python3 observation/release_v360.py measured
```

최초 실행 순서는 `build`, `smoke`, `pilot`, `stats`, `freeze`, `measured`다.
새 namespace에서만 build/freeze를 실행한다. 기존 plan.json이 있으면 거부한다.
measured는 이미 존재하는 valid 결과와 설정을 대조하고 건너뛰며, invalid 기록은
중단 대상으로 보존한다. 기존 결과를 다시 측정하려면 별도 namespace를 만든다.

stats는 각 버전 헤더로 만든 explicit API 진단이다. v3.6.0에서는 새 이름의
stats_merge_on_collect와 stats_merge_threshold를 사용한다. 성능 실행은
동일 executable에 LD_PRELOAD를 적용하고 MIMALLOC 환경변수는 비운다.

본 측정이 끝난 뒤 다음 두 별도 진단을 실행한다. 같은 시간에 다른 측정과 겹치지 않는다.

```powershell
docker run --rm --pull=never --network none --cpuset-cpus=0,2,4,6,8,10 --cpuset-mems=0 --mount $mount --workdir /work $image python3 observation/v360_diagnostics.py
docker run --rm --pull=never --network none --cpuset-cpus=0,2,4,6,8,10 --cpuset-mems=0 --mount $mount --workdir /work $image python3 observation/v360_reclaim_control.py
python observation/analyze_v360.py
```

원자료는 `results/release-v360-v1/`, 고정 계획·집계·진단 기록은
`experiments/release-v360-v1/`, 그림·표는 `docs/v360/`에 저장한다.
관찰은 각 기본 조건 3회 중앙값/범위이며 통계적 동등성 시험이 아니다.
제어 프로그램의 CPU 배치를 비롯한 세부 조건은 계획과 원자료를 따른다.
