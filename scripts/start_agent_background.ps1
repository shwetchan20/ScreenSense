param(
  [string]$PythonExe = ".\.venv\Scripts\python.exe",
  [string]$LogFile = "runtime\agent.out.log"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $PythonExe)) {
  throw "Python executable not found at '$PythonExe'."
}
if (-not (Test-Path ".env")) {
  throw ".env missing."
}
if (-not (Test-Path "runtime")) {
  New-Item -ItemType Directory -Path "runtime" | Out-Null
}

$fullPython = (Resolve-Path $PythonExe).Path
$fullLog = Join-Path (Get-Location) $LogFile

Write-Host "[background] Launching ScreenSense background process..."
Start-Process -FilePath $fullPython `
  -ArgumentList "aria_watchdog.py" `
  -WorkingDirectory (Get-Location).Path `
  -RedirectStandardOutput $fullLog `
  -RedirectStandardError $fullLog

Write-Host "[background] Started. Logs: $fullLog"
