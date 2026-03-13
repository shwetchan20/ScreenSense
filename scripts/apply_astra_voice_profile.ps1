param(
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $EnvFile)) {
    throw "Missing $EnvFile. Create it first (Copy-Item .env.example .env)."
}

$text = Get-Content $EnvFile -Raw

function Set-Or-Add([string]$Key, [string]$Value) {
    $script:text = if ($script:text -match "(?m)^$Key=") {
        [regex]::Replace($script:text, "(?m)^$Key=.*$", "$Key=$Value")
    } else {
        $script:text.TrimEnd() + "`r`n$Key=$Value`r`n"
    }
}

Set-Or-Add "ENABLE_TTS" "true"
Set-Or-Add "VOICE_PRESET" "astra_like"
Set-Or-Add "VOICE_PROVIDER" "edge_tts"
Set-Or-Add "VOICE_STYLE" "friendly"
Set-Or-Add "VOICE_RATE_WPM" "182"
Set-Or-Add "VOICE_EDGE_NAME" "en-US-JennyNeural"
Set-Or-Add "VOICE_EDGE_RATE" "+8%"
Set-Or-Add "VOICE_EDGE_PITCH" "+0Hz"
Set-Or-Add "VOICE_ADAPTIVE_MODE" "true"
Set-Or-Add "VOICE_REPEAT_WINDOW_SECONDS" "90"

Set-Content -Path $EnvFile -Value $text -Encoding UTF8

Write-Host "Applied Astra-like voice profile to $EnvFile"
