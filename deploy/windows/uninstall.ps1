#Requires -RunAsAdministrator
# Removes the TalabaBot background tasks and stops the running app and bot.
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$taskPath = '\TalabaBot\'
Get-ScheduledTask -TaskPath $taskPath -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $_.TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskPath $taskPath -TaskName $_.TaskName -Confirm:$false
}
& (Join-Path $PSScriptRoot 'restart.ps1') | Out-Null
'TalabaBot tasks removed and processes stopped.'
