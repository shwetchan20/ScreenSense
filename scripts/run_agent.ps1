param(
  [string]$PythonExe = ".\.venv\Scripts\python.exe",
  [switch]$CheckOnly,
  [switch]$Watchdog
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

Write-Host "[run_agent] Python: $PythonExe"
Write-Host "[run_agent] Checking config import..."
& $PythonExe -c "from screensense.config import load_settings; s=load_settings(); print('ok', s.reasoning_mode, s.voice_provider)"

Write-Host "[run_agent] Checking Ollama endpoint..."
try {
  $ollamaOk = $false
  $resp = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
  if ($resp.models) { $ollamaOk = $true }
  if ($ollamaOk) {
    Write-Host "[run_agent] Ollama detected."
  } else {
    Write-Host "[run_agent] Ollama reachable but no models listed."
  }
} catch {
  Write-Host "[run_agent] Ollama not reachable (ok if REASONING_MODE=gemini)."
}

if ($CheckOnly) {
  Write-Host "[run_agent] CheckOnly complete."
  exit 0
}

Write-Host "[run_agent] Starting ScreenSense..."
if ($Watchdog) {
  & $PythonExe aria_watchdog.py
} else {
  & $PythonExe -m screensense.app
}
