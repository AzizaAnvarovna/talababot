# Restarts the web app and the bot (for example after updating the code).
# The runner loops in run.ps1 start them again within about 10 seconds.
# A venv python.exe is a launcher that starts the real interpreter as a child,
# so processes are matched by command line and stopped together with their children.
$pattern = '-m bot\.main|app\.main:app'
$processes = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='uvicorn.exe'" |
    Where-Object { $_.CommandLine -match $pattern })
foreach ($process in $processes) {
    taskkill.exe /PID $process.ProcessId /T /F 2>$null | Out-Null
}
"Stopped $($processes.Count) process(es); they restart in about 10 seconds."
