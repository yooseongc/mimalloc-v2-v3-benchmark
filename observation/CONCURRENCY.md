# 동시 처리 관찰 실행

활성 후속 설계: [concurrency-plan](../docs/concurrency-plan.md).
비교 대상은 **v2.1.2, v3.5.0, v3.5.3**이다. 폐기된 benchmark/ 및 scripts/ 실행기를
사용하지 않는다. sequential lifecycle.cpp 및 그 동결 자료도 수정하지 않는다.

`concurrent.cpp`가 독립 SPSC 인계 공간에서 할당·전체 쓰기와 다른 스레드의
검증·해제를 겹쳐 실행한다. `run_concurrent.py`는 외부 메모리 관찰과 무결성 검증을
수행한다. `analyze_concurrent.py`는 중앙값·범위, RSS 시계열 및 별도 retained 대조군을
보고한다. retained 속도를 기본 실행 시간에서 빼지 않는다.

## 실행 환경

Rocky Linux image ID:
`sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877`.
라이브러리는 새 memory-behavior 작업에서 빌드한 기본 Release 산출물이며,
`experiments/concurrency-v1/artifacts.json`의 commit·library SHA와 일치해야 한다.
처음 준비하는 환경에서는 `observation/run.py build`가 해당 세 라이브러리를 만든다.
관측 당시 이미지·라이브러리·바이너리가 없는 환경의 새 빌드는 새 artifact 기록과
새 실험 namespace로 분리해야 한다. 기존 동결 파일을 덮어써 원자료와 섞지 않는다.

PowerShell에서 저장소 루트를 현재 디렉터리로 두고 사용한다.

```powershell
$image = 'sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877'
$mount = 'type=bind,source=C:\Users\user\workspace\mimalloc-test,target=/work'
docker run --rm --pull=never --network none --ulimit core=0 --cpuset-cpus=0,2,4,6,8,10 --cpuset-mems=0 --mount $mount --workdir /work $image python3 observation/run_concurrent.py measured
```

마지막 인자를 `controls`로 바꾸면 30개 별도 대조군을 실행한다.
이미 존재하는 valid 결과는 설정을 대조한 뒤 건너뛰며 덮어쓰지 않는다.
invalid 파일이 있으면 중단한다. 실패를 삭제해 숨기는 방식으로 재실행하지 않는다.

이번 신규 namespace의 최초 실행 순서는 `build`, `smoke`, `pilot`, `freeze`,
`measured`, `controls`였다. freeze는 크기별 작업량과 순서를 미리 고정하며
이미 동결된 plan이 있으면 다시 쓰지 않는다. build 역시 기존 원자료 보존 중에는
다시 호출하지 않는다.

분석은 측정이 모두 끝난 다음 호스트에서 실행한다.

```powershell
python observation/analyze_concurrent.py
```

## 검증과 지표

- worker A0/B2, 두 번째 쌍 A4/B6, 제어8, 외부 관찰10. WSL2 가상 CPU 환경이다.
- 각 fresh process의 실제 malloc/free 라이브러리 경로·버전·maps와 SHA를 검증한다.
- 모든 객체의 앞뒤 identity, 예상 체크섬, 처리 개수, 최종 생존량을 검증한다.
  smoke는 전체 payload도 읽어 검증한다.
- 처음 공간을 채우는 시간은 제외하고 해당 객체의 해제는 포함한다.
  총 완료 수와 timed 구간의 신규 할당 수는 구분해서 저장한다.
- worker CPU는 CLOCK_THREAD_CPUTIME_ID로 측정하며 대기 비용도 포함한다.
- RSS 샘플은 약 100 ms 간격, smaps_rollup은 준비·완료·idle 경계에서 수집한다.
  page fault는 프로세스의 두 경계 사이 차이다.
- 각 쌍의 슬롯은 256개 객체 단위다. 생존량은 배치 진행 공개와 읽기 시차가 있는
  근사값이다. 총 공간을 채운 초기 상태와 0으로 배출한 종료 상태는 정확히 확인한다.
- `wait_polls`는 busy-wait 횟수다. 대기 시간이나 stall 비율로 환산하지 않는다.
- retained는 준비한 객체를 유지하며 다시 쓴다. 객체 배치와 캐시 재사용도 기본
  실행과 다르므로 malloc/free의 순수 비용을 추출하는 대조군이 아니다.
- 전체 쓰기, identity 검증, 인계와 포인터 배열 비용을 포함한 작업 흐름의 결과다.
  개별 malloc/free 지연시간, 실제 서비스 요청 latency로 해석하지 않는다.

원자료: `results/concurrency-v1/` (Git 제외).
고정 설정·집계·hash 목록: `experiments/concurrency-v1/`.
최초 1 MiB smoke 중 잘못된 4 KiB/2쌍 입력을 거부한 기록도 보존한다.
