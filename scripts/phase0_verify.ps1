param(
  [string]$PythonExe = ".\.venv\Scripts\python.exe",
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $PythonExe)) {
  throw "Python executable not found at '$PythonExe'. Create/activate .venv first."
}
if (-not (Test-Path ".env")) {
  throw ".env not found. Copy .env.example to .env and configure required values."
}
if (-not (Test-Path "runtime")) {
  New-Item -ItemType Directory -Path "runtime" | Out-Null
}

Write-Host "[phase0_verify] 1) Check config + endpoints"
powershell -ExecutionPolicy Bypass -File .\scripts\run_agent.ps1 -CheckOnly -PythonExe $PythonExe

if (-not $SkipTests) {
  Write-Host "[phase0_verify] 2) Run tests"
  & $PythonExe -m pytest -q
} else {
  Write-Host "[phase0_verify] 2) Skipping tests"
}

Write-Host "[phase0_verify] 3) Show Phase 0 metrics (last events)"
& $PythonExe .\scripts\phase0_metrics.py

Write-Host ""
Write-Host "[phase0_verify] Done."

