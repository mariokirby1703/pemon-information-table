$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.sync-state\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Install .sync-state\venv and requirements.txt first.' }
$taskScript = Join-Path $PSScriptRoot 'start_daily_sync.ps1'
$powershellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$action = New-ScheduledTaskAction -Execute $powershellExe -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $taskScript) -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At '20:00'
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 12)
Register-ScheduledTask -TaskName 'Pemon Daily Sync' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Daily Pemon metadata sync at 20:00 local time, newest first, five seconds between GD requests.' -Force | Out-Null
Get-ScheduledTask -TaskName 'Pemon Daily Sync' | Get-ScheduledTaskInfo | Select-Object NextRunTime, LastTaskResult
