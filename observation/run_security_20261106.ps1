param([string[]]$Stages = @('build','smoke','pilot','freeze','measured'))
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$image = 'sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877'
$logs = Join-Path $repo 'experiments/security-20261106-v1/logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
foreach ($stage in $Stages) {
    $log = Join-Path $logs ($stage + '-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss') + '.log')
    $runnerArgs = @('observation/security_20261106.py', $stage)
    if ($stage -eq 'diagnostics') { $runnerArgs = @('observation/security_syscalls.py') }
    & docker run --rm --pull=never --network none --memory=4g --memory-swap=4g --cpuset-cpus=0,2,4,6,8,10 --cpuset-mems=0 --mount "type=bind,source=$repo,target=/work" --workdir /work $image python3 @runnerArgs 2>&1 | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw "$stage failed; see $log" }
}
