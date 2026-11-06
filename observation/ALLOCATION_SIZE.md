# 할당 크기 확대 관찰 재현

설계: `docs/allocation-size-plan.md`. 실행기: `observation/allocation_size.py`.
고정 계약: `experiments/allocation-size-v1/{preparation,plan,artifacts}.json`.

기존 purge-delay-v1에서 생성한 controller·소스와 release-v360-v1에서 빌드한
라이브러리가 필요하다. 원본을 수정하지 않고 별도 소스와 공통 실행파일을 생성한다.
prepare → smoke → pilot → freeze → measured 순서이며 이미 존재하는 준비·동결
계약을 덮어쓰지 않는다. 완전히 새 관측은 새 namespace와 계약을 사용한다.

프로젝트 루트의 PowerShell에서 마지막 인자를 위 단계에 맞게 바꿔 실행한다.

```powershell
docker run --rm --pull=never --network none --cpuset-cpus=0,2,4,6,8,10 --cpuset-mems=0 --mount "type=bind,source=${PWD},target=/work" --workdir /work sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877 python3 observation/allocation_size.py measured
python -X utf8 observation/analyze_allocation_size.py
```

분석에는 Python 3.9 이상, matplotlib와 numpy가 필요하다.
원자료는 `results/allocation-size-v1/{smoke,pilot,measured}/`, 원자료 SHA 목록은
`experiments/allocation-size-v1/raw-index.json`에 기록된다.
기존 유효 실행은 보존하고 실패 실행은 삭제하거나 대체하지 않는다.

본 관찰에서 공통 완료 payload는 750.625 GiB이며 크기에 따라 객체 수만 바뀐다.
이는 동시에 보유하는 양이 아니다. 생존 요청량 상한은 128 MiB이고, 실제 생존량은
더 작을 수 있다. timed 구간의 새 쓰기는 초기 적재 0.125 GiB를 뺀 750.5 GiB다.
