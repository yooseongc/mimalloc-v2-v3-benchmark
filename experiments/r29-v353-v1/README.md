# r29 v3.5.3 comparison

See [contract.md](contract.md), [plan.json](plan.json), and
[the report](../../docs/experiment-report-r29.md) for current status.
The official v3.5.3 tag is fixed to
`d4881d338125e1cb7c47ba4cfb398d6f7c0c8d45`; old measured data are not reused.

## Reproduce or resume

Use the existing fixed Rocky Linux 8 image and the exact artifacts in the plan.
Source setup: `bash scripts/fetch_sources.sh`; build v3.5.3 inside that image
with `bash scripts/build_mimalloc.sh v3.5.3`. The build script refuses reuse of
an existing build directory. Do not rebuild or overwrite a frozen benchmark
binary while measurements are in progress.

On Linux or WSL with Docker access:

```bash
bash scripts/container/run_active.sh --stage measured --status
bash scripts/container/run_active.sh --stage measured --execute --max-blocks 0
```

On this Windows workspace, the equivalent PowerShell command is:

```powershell
docker run --rm --network none --cpuset-cpus=0,2,4,6,8,10,12,14 --cpuset-mems=0 `
  --mount 'type=bind,source=C:\Users\user\workspace\mimalloc-test,target=/work' `
  --workdir /work `
  sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877 `
  python3 -u scripts/run_comparison_r29.py --stage measured --execute --max-blocks 0
```

Omit `--execute` for command preview; omit `--max-blocks 0` to run one matched
block. Each arm has a timeout, each result is durable, and a namespace lock
prevents concurrent invocations. Completed arms are skipped on resume.

Setup used `--stage smoke` (all profiles), followed by `--stage pilot --profile
core --profile latency` (three repetitions). Those stages used draft-plan.json
and draft-contract.md. Do not rewrite their evidence after calibration. The
freeze script requires the full draft evidence, then fixes operation counts
and repetitions before measured execution. A frozen plan cannot be regenerated
by the draft generator or refrozen by the freeze script. New artifacts or
settings require a new revision and namespace.

Report generation on a host Python 3.8+ environment:

```bash
# Install before measurements, or after they finish.
python -m pip install -r requirements-analysis.txt
python -m unittest discover -s benchmark/tests -p 'test_*.py'
python scripts/analyze_r29.py
```

All analysis consumes only r29 measured records, validates their plan/commit
identity and core checksums, compares complete triplets, and retains invalid
attempts. Numerical summaries are in `results/summaries/summary-r29.json`,
figures in `docs/r29-plots/`, and raw records in `results/active/r29-v353-v1/`.
Large raw files are ignored by Git; raw-index.json records their hashes.
