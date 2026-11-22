param([string[]]$Stages = @('smoke','pilot','stats','freeze','measured','purge','sizes'))
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$image = 'sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877'
$logs = Join-Path $repo 'experiments/release-v361-v1/logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
function Invoke-Stage([string]$Runner, [string]$Action) {
    $log = Join-Path $logs ($Runner + '-' + $Action + '-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss') + '.log')
    & docker run --rm --pull=never --network none --cpuset-cpus=0,2,4,6,8,10 --cpuset-mems=0 --mount "type=bind,source=$repo,target=/work" --workdir /work $image python3 "observation/$Runner.py" $Action 2>&1 | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw "$Runner $Action failed; see $log" }
}
foreach ($stage in $Stages) {
    if ($stage -eq 'purge') {
        foreach ($action in @('prepare','smoke','measured')) { Invoke-Stage 'purge_delay_v361' $action }
    } elseif ($stage -eq 'sizes') {
        foreach ($action in @('prepare','smoke','pilot','freeze','measured')) { Invoke-Stage 'allocation_size_v361' $action }
    } else { Invoke-Stage 'release_v361' $stage }
}
