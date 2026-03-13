param(
  [string]$EnvPath = ".env"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvPath)) {
  throw "$EnvPath not found."
}

$lines = Get-Content $EnvPath

function Set-EnvValue {
  param([string]$Key, [string]$Value)
  $pattern = "^$([regex]::Escape($Key))="
  $found = $false
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match $pattern) {
      $lines[$i] = "$Key=$Value"
      $found = $true
      break
    }
  }
  if (-not $found) {
    $script:lines += "$Key=$Value"
  }
}

Set-EnvValue "REASONING_MODE" "hybrid"
Set-EnvValue "LOCAL_LLM_PROVIDER" "ollama"
Set-EnvValue "LOCAL_LLM_MODEL" "qwen2.5:latest"
Set-EnvValue "LOCAL_LLM_BASE_URL" "http://127.0.0.1:11434"
Set-EnvValue "LOCAL_LLM_ESCALATE_CONFIDENCE_THRESHOLD" "0.55"
Set-EnvValue "HYBRID_FORCE_GEMINI_ON_CRITICAL" "false"

Set-EnvValue "ENABLE_TTS" "true"
Set-EnvValue "VOICE_PROVIDER" "edge_tts"
Set-EnvValue "VOICE_AGGRESSIVENESS" "chatty"

Set-EnvValue "DIFF_THRESHOLD" "8"
Set-EnvValue "FAST_PATH_ENABLED" "false"
Set-EnvValue "IMPACT_SCORE_THRESHOLD" "0.50"
Set-EnvValue "INTERRUPT_COOLDOWN_SECONDS" "10"
Set-EnvValue "PRODUCT_MODE" "ask"

Set-Content -Path $EnvPath -Value $lines
Write-Host "[profile] Applied local reliable profile to $EnvPath"
