# Starts one TalabaBot service and restarts it whenever it stops.
# Used by the Task Scheduler tasks that deploy\windows\install.ps1 registers.
param([Parameter(Mandatory = $true)][ValidateSet('web', 'bot')][string]$Service)

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
$env:PYTHONUTF8 = '1'
$python = Join-Path $root '.venv\Scripts\python.exe'
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir "$Service.log"
$maxLogBytes = 10MB

function Write-Log([string]$Message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$Service] $Message`r`n"
    [System.IO.File]::AppendAllText($log, $line)
}

function Invoke-Logged([string]$Arguments) {
    # cmd keeps Python's UTF-8 output as raw bytes in the log file.
    cmd.exe /c "`"$python`" $Arguments >> `"$log`" 2>&1"
    return $LASTEXITCODE
}

while ($true) {
    if ((Test-Path $log) -and (Get-Item $log).Length -gt $maxLogBytes) {
        Move-Item -Force $log "$log.1"
    }
    Write-Log 'started'
    if ($Service -eq 'web') {
        $code = Invoke-Logged '-m alembic upgrade head'
        if ($code -eq 0) {
            $code = Invoke-Logged '-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning'
        }
    }
    else {
        $code = Invoke-Logged '-m bot.main'
    }
    Write-Log "stopped with exit code $code, restarting in 10 s"
    Start-Sleep -Seconds 10
}
