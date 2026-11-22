# v3.7.0 여섯 버전 비교 재현

계획: [v370-plan](../docs/v370-plan.md). 기존 동결 자료는 수정하지 않는다.
소스 SHA는 계획과 새 lifecycle/artifacts.json에 기록한다.
공식 v3.7.0 태그를 extern/mimalloc-v3.7.0에 checkout한 뒤 프로젝트 루트에서:

```powershell
./observation/run_v370_suite.ps1 -Stages build
./observation/run_v370_suite.ps1
python observation/analyze_v370.py
python observation/plot_v370_memory.py
python observation/analyze_purge_delay_v370.py
python observation/analyze_allocation_size_v370.py
python observation/verify_v370.py
python observation/report_v370.py
```

분석 환경은 Python 3.9 이상과 matplotlib가 필요하다. 실행 컨테이너는 기존 고정 Rocky
이미지이며 Python 3.6 호환 runner를 사용한다. 실행은 순차적이며 오류 시 중단한다.
기존 namespace에서 build/prepare/freeze를 다시 하지 않는다. 측정 재개는 각 runner의
measured 액션만 실행하며 valid 결과의 설정을 확인하고 건너뛴다. 실패 기록은 지우지 않는다.
독립 새 측정을 하려면 namespace를 새로 만든다.

기본 결과: results/release-v370-v1, experiments/release-v370-v1, docs/v370.
purge: results/purge-delay-v370-v1, experiments/purge-delay-v370-v1, docs/purge-delay-v370.
크기: results/allocation-size-v370-v1, experiments/allocation-size-v370-v1, docs/allocation-size-v370.
stats는 explicit API 진단이다. 기본 timed workload는 공통 실행파일 + LD_PRELOAD다.
v3.7.0의 통계 병합 임계값 기본 4 MiB를 검증하며 v3.6.0의 512 KiB와 구분한다.
