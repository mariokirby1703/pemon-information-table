param([switch]$Check, [switch]$Force, [switch]$All)
$projectRoot = Split-Path -Parent $PSScriptRoot
$syncArgs = @((Join-Path $PSScriptRoot 'run_daily_sync.py'))
if ($Check) { $syncArgs += '--check' }
if ($Force) { $syncArgs += '--force' }
if ($All) { $syncArgs += '--all' }
& (Join-Path $projectRoot '.sync-state\venv\Scripts\python.exe') @syncArgs
exit $LASTEXITCODE
