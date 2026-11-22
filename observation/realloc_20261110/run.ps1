param([string[]]$Stages = @('build','smoke','pilot','preflight','freeze','measured','analyze'))
$ErrorActionPreference='Stop'
$repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$image='sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877'
foreach ($stage in $Stages) {
  & docker run --rm --pull=never --network none --memory=4g --memory-swap=4g --cpuset-cpus=0,2 --cpuset-mems=0 --mount "type=bind,source=$repo,target=/work" --workdir /work $image python3 observation/realloc_20261110/run.py $stage
  if ($LASTEXITCODE -ne 0) { throw "$stage failed" }
}
