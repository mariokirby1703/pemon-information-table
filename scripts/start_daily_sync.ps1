$projectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $projectRoot '.sync-state\venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'run_daily_sync.py')
exit $LASTEXITCODE
