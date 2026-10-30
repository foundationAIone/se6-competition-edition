param([int]$Port=0,[switch]$Simulation)
$ErrorActionPreference='Stop'
$launcher=Join-Path $PSScriptRoot 'tools/run_dashboard.py'
$arguments=@('-B',$launcher,'--port',[string]$Port)
if($Simulation){$arguments+='--simulation'}
& python @arguments
exit $LASTEXITCODE
