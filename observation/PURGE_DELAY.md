# 동일 purge 대기시간 관찰 재현

설계: `docs/purge-delay-plan.md`. 동결 계약: `experiments/purge-delay-v1/plan.json`.
사용한 라이브러리와 커밋·SHA: 같은 디렉터리의 `artifacts.json`.
앞선 `release-v360-v1`에서 준비한 라이브러리가 필요하다.

PowerShell에서 프로젝트 루트 기준으로 실행한다. 마지막 인자를 `prepare`,
`smoke`, `measured` 순서로 바꾼다. 이미 동결된 namespace에서 prepare는 거부된다.
measured는 완료된 유효 결과를 보존한다. 완전히 새 측정은 새 namespace와 새 동결 계약으로 한다.

```powershell
docker run --rm --pull=never --network none --cpuset-cpus=0,2,4,6,8,10 --cpuset-mems=0 --mount "type=bind,source=${PWD},target=/work" --workdir /work sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877 python3 observation/purge_delay.py measured
python -X utf8 observation/analyze_purge_delay.py
```

분석은 Python 3.9 이상, matplotlib 및 numpy가 필요하다. 분석 스크립트는 동결 hash,
실행 순서, 라이브러리·실행파일 SHA, 적용 옵션, 성공 상태를 다시 확인한다.
원시 데이터는 `results/purge-delay-v1/{defaults,smoke,measured}/`에 있으며,
`experiments/purge-delay-v1/raw-index.json`에 각각의 SHA를 기록한다.
