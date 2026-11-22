param([switch]$Check, [switch]$Watch)
$projectRoot = Split-Path -Parent $PSScriptRoot
$syncArgs = @((Join-Path $PSScriptRoot 'run_daily_sync.py'))
if ($Check) { $syncArgs += '--check' }
if ($Watch) { $syncArgs += '--watch' }
& (Join-Path $projectRoot '.sync-state\venv\Scripts\python.exe') @syncArgs
exit $LASTEXITCODE
