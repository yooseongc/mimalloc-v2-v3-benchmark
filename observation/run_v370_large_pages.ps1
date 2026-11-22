param([string[]]$Stages = @('prepare','smoke','pilot','freeze','measured'))
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$image = 'sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877'
$logs = Join-Path $repo 'experiments/v370-large-pages-v1/logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
foreach ($stage in $Stages) {
    $log = Join-Path $logs ($stage + '-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss') + '.log')
    & docker run --rm --pull=never --network none --memory=6g --memory-swap=6g --cpuset-cpus=0,2,4,6,8,10 --cpuset-mems=0 --mount "type=bind,source=$repo,target=/work" --workdir /work $image python3 observation/v370_large_pages.py $stage 2>&1 | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw "$stage failed; see $log" }
}
