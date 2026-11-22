$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$image = 'sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877'
& docker run --rm --pull=never --network none --memory=6g --memory-swap=6g --cpuset-cpus=0,2,4,6,8,10 --cpuset-mems=0 --mount "type=bind,source=$repo,target=/work" --workdir /work $image python3 /work/observation/dev3_20261122.py
if ($LASTEXITCODE -ne 0) { throw 'Experiment failed' }
& python "$PSScriptRoot/report_dev3_20261122.py"
if ($LASTEXITCODE -ne 0) { throw 'Verification failed' }
