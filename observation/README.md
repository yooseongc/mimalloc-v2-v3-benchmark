# 메모리 흐름 관찰 프로그램

기존 하네스와 실행기·분석기를 사용하지 않는 새 구현이다.
후속 동시 처리·규모 확대 프로그램은 [CONCURRENCY.md](CONCURRENCY.md)를 따른다.

- `lifecycle.cpp`: A가 객체를 할당·쓰기하고 A 또는 B가 해제한다. 단계 밖에서
  전체 생존 payload를 검증한다. 두 worker는 마지막까지 살아 있다.
- `run.py`: 외부 프로세스에서 단계 명령을 보내고 메모리를 관찰한다.
- `check.py`: 올바른 생명주기와 잘못된 상태의 거부를 확인한다.
- `collect_check.py`: 주 관찰 후, A가 `mi_collect(true)`를 한 번 호출하는 별도 진단이다.
- `analyze.py`: 새 원자료만 읽어 단계별 비용·메모리 흐름 표와 그림을 생성한다.

고정 이미지:
`sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877`.
Rocky Linux 8.9, GCC 8.5.0. 실행 cpuset은 0,2,4,6, mems는 0이다.
버전 source HEAD와 tracked source 상태를 검사하고 라이브러리를
`build/observation-v1/`에 별도로 빌드했다.

PowerShell에서 실행 또는 완료 상태 재확인:

```powershell
docker run --rm --pull=never --network none --ulimit core=0 --cpuset-cpus=0,2,4,6 --cpuset-mems=0 --mount 'type=bind,source=C:\Users\user\workspace\mimalloc-test,target=/work' --workdir /work sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877 python3 observation/run.py measured
```

이미 완료된 파일은 덮어쓰지 않는다. 같은 명령의 마지막 부분을
`python3 observation/collect_check.py`로 바꾸면 별도 collect 진단을 실행한다.
분석은 호스트에서 `python observation/analyze.py`로 실행한다.
분석용 Python에 matplotlib가 필요하며 실제 측정 프로세스에는 사용하지 않는다.

처음 구축할 때의 순서는 컨테이너 안에서 `python3 observation/run.py build`,
`python3 observation/check.py`, `python3 observation/run.py smoke`,
`python3 observation/run.py pilot`, 실행 조건 확정 순서였다.
동결 이후에는 빌드를 다시 만들거나 기존 파일을 바꾸지 않는다.
다른 환경에서 다시 구축할 경우 별도 결과 디렉터리·계획으로 식별한다.

원자료는 `results/memory-behavior-v1/` 아래에 있다. `measured`와
`collect-check`를 같은 반복 집합으로 합치지 않는다. CPU·fault·checksum·실제
시각·RSS·VmHWM·VmSwap·실제 라이브러리 정보를 실행별 JSON에 남긴다.
3회 탐색은 성능 우열을 확정하는 검정이 아니다.
