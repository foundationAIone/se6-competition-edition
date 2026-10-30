param([string]$PythonExecutable,[int]$Port=0,[string]$Store,[string]$Attestation,[switch]$VerifyOnly)
$ErrorActionPreference='Stop'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONNOUSERSITE='1'
$app=Join-Path $PSScriptRoot 'app'
if(-not $PythonExecutable){
  $venv=Join-Path $PSScriptRoot '.release-env'
  $PythonExecutable=Join-Path $venv 'Scripts\python.exe'
  if(-not (Test-Path -LiteralPath $PythonExecutable)){
    & py -3.14 -m venv $venv
    if($LASTEXITCODE -ne 0){throw 'CPython3.14 creation failed; nothing started'}
    & $PythonExecutable -m pip install --no-index --find-links (Join-Path $PSScriptRoot 'wheelhouse-windows-py314') --require-hashes -r (Join-Path $app 'requirements-windows-py314.lock')
    if($LASTEXITCODE -ne 0){throw 'Offline dependency install failed; nothing started'}
  }
}
& $PythonExecutable -B -c "import sys,importlib.metadata as m; assert sys.version_info[:2]==(3,14); assert m.version('pydantic')=='2.12.4'; assert m.version('pydantic_core')=='2.41.5'"
if($LASTEXITCODE -ne 0){throw 'Target dependency mismatch; nothing started'}
& $PythonExecutable -B (Join-Path $app 'tools\verify_release.py')
if($LASTEXITCODE -ne 0){throw 'Source integrity failure; nothing started'}
$evidence=Join-Path $PSScriptRoot 'evidence\current'
$pins=Get-Content -LiteralPath (Join-Path $evidence 'MANIFEST.json') -Raw | ConvertFrom-Json
foreach($member in $pins.files.PSObject.Properties){
  $target=Join-Path $evidence $member.Name
  if((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $member.Value){throw 'Saved evidence pin mismatch'}
}
if($VerifyOnly){Write-Host 'VERIFIED: source, target dependencies and saved evidence; zero inference';exit 0}
if(-not $Store){$Store=Join-Path $PSScriptRoot 'runtime'}
$argsList=@('-B',(Join-Path $app 'tools\run_dashboard.py'),'--port',[string]$Port,'--store',$Store,
  '--model-workflow-evidence',(Join-Path $evidence 'model-workflow.json'),'--model-workflow-evidence-sha256',$pins.files.'model-workflow.json',
  '--agent-realization-evidence',(Join-Path $evidence 'agent-realization.json'),'--agent-realization-evidence-sha256',$pins.files.'agent-realization.json',
  '--research-preparation-evidence',(Join-Path $evidence 'research-result.json'),'--research-preparation-evidence-sha256',$pins.files.'research-result.json')
if($Attestation){$argsList+=@('--attestation',$Attestation)}
Write-Host 'Local test build. Default paid allowance: zero. Open the printed JUDGE_URL/demo/comparison/.'
& $PythonExecutable @argsList
exit $LASTEXITCODE
