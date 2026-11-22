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

# Fast rating watcher; the daily complete refresh remains unchanged.
$watchAction = New-ScheduledTaskAction -Execute $powershellExe -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -Watch' -f $taskScript) -WorkingDirectory $projectRoot
$watchTrigger = New-ScheduledTaskTrigger -Once -At '00:15' -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName 'Pemon Rating Watch' -Action $watchAction -Trigger $watchTrigger -Principal $principal -Settings $settings -Description 'Hourly Geometry Dash rating and newly rated Platformer Demon checks.' -Force | Out-Null
Get-ScheduledTask -TaskName 'Pemon Rating Watch' | Get-ScheduledTaskInfo | Select-Object NextRunTime, LastTaskResult
