$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.sync-state\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Install .sync-state\venv and requirements.txt first.' }
$taskScript = Join-Path $PSScriptRoot 'start_daily_sync.ps1'
$powershellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

# One logon trigger. The Python runner enforces one successful run
# per Europe/Berlin calendar day, including across Windows restarts.
$action = New-ScheduledTaskAction -Execute $powershellExe -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $taskScript) -WorkingDirectory $projectRoot
$loginTrigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 12)
Register-ScheduledTask -TaskName 'Pemon Daily Sync' -Action $action -Trigger $loginTrigger -Principal $principal -Settings $settings -Description 'Once-per-day lightweight platformer demon changes at Windows user logon.' -Force | Out-Null

# Remove the retired hourly watcher, so there can be no duplicate schedule.
$oldTask = Get-ScheduledTask -TaskName 'Pemon Rating Watch' -ErrorAction SilentlyContinue
if ($oldTask) {
    Unregister-ScheduledTask -TaskName 'Pemon Rating Watch' -Confirm:$false
}
Get-ScheduledTask -TaskName 'Pemon Daily Sync' | Get-ScheduledTaskInfo | Select-Object NextRunTime, LastTaskResult
