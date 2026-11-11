#Requires -RunAsAdministrator
# Registers TalabaBot as background tasks on this Windows computer:
#   web and bot start at boot (no login needed), backup runs daily at 02:30.
# Run once from an administrator PowerShell:  .\deploy\windows\install.ps1
param([string]$User = "$env:USERDOMAIN\$env:USERNAME")
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Virtual environment not found: $python" }
if (-not (Test-Path (Join-Path $root '.env'))) { throw '.env not found in project folder.' }
$taskPath = '\TalabaBot\'

# S4U: runs as this user without a stored password and without anyone logging in.
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType S4U -RunLevel Limited
$serviceSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

foreach ($service in 'web', 'bot') {
    $arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden " +
        "-File `"$root\deploy\windows\run.ps1`" -Service $service"
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $root
    Register-ScheduledTask -TaskPath $taskPath -TaskName "TalabaBot-$service" -Action $action `
        -Trigger (New-ScheduledTaskTrigger -AtStartup) -Principal $principal -Settings $serviceSettings `
        -Force | Out-Null
}

$backupSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$backupLog = Join-Path $root 'logs\backup.log'
$backupAction = New-ScheduledTaskAction -Execute 'cmd.exe' -WorkingDirectory $root `
    -Argument "/c set `"PYTHONUTF8=1`"&& `"$python`" -m app.backup >> `"$backupLog`" 2>&1"
Register-ScheduledTask -TaskPath $taskPath -TaskName 'TalabaBot-backup' -Action $backupAction `
    -Trigger (New-ScheduledTaskTrigger -Daily -At '02:30') -Principal $principal `
    -Settings $backupSettings -Force | Out-Null

# Never sleep on mains power, and keep running when the laptop lid is closed on mains power.
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT

New-Item -ItemType Directory -Force (Join-Path $root 'logs') | Out-Null
Start-ScheduledTask -TaskPath $taskPath -TaskName 'TalabaBot-web'
Start-ScheduledTask -TaskPath $taskPath -TaskName 'TalabaBot-bot'
Get-ScheduledTask -TaskPath $taskPath | Select-Object TaskName, State
