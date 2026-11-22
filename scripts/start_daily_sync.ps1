param([switch]$Check)
$projectRoot = Split-Path -Parent $PSScriptRoot
$syncArgs = @((Join-Path $PSScriptRoot 'run_daily_sync.py'))
if ($Check) { $syncArgs += '--check' }
& (Join-Path $projectRoot '.sync-state\venv\Scripts\python.exe') @syncArgs
exit $LASTEXITCODE
