#!/usr/bin/env pwsh
# Run ARIA Local Runtime (Master Architecture)

Write-Host "=== Starting ARIA (Local Vision Runtime) ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "Configuring GPU-first runtime..." -ForegroundColor Yellow
$env:OLLAMA_LLM_LIBRARY = "cuda"
$env:OLLAMA_FLASH_ATTENTION = "1"
$env:CUDA_VISIBLE_DEVICES = "0"
$env:ARIA_DISABLE_TELEGRAM = "1"
$env:ARIA_TELEGRAM_TOKEN = ""
$env:ARIA_TELEGRAM_CHAT_ID = ""
$env:TELEGRAM_BOT_TOKEN = ""
$env:TELEGRAM_CHAT_ID = ""
$env:ARIA_VLM_MODEL = "qwen3-vl:2b"
$env:ARIA_VLM_NUM_CTX = "1024"
$env:ARIA_SCREENSHOT_MAX_WIDTH = "640"
$env:ARIA_SCREENSHOT_MAX_HEIGHT = "360"
$env:ARIA_SCREEN_VLM_NUM_PREDICT = "384"
$env:ARIA_SCREEN_VLM_TIMEOUT_SECONDS = "180"
$modelName = $env:ARIA_VLM_MODEL

Write-Host "Checking Ollama status..." -ForegroundColor Yellow
$response = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -Method GET -TimeoutSec 2
Write-Host "Ollama is running" -ForegroundColor Green

Write-Host "Checking $modelName model..." -ForegroundColor Yellow
$models = $response.Content | ConvertFrom-Json
$hasModel = $models.models | Where-Object { $_.name -like "$modelName*" }
if (-not $hasModel) {
    throw "$modelName not found. Run: ollama pull $modelName"
}
Write-Host "$modelName is available" -ForegroundColor Green
Write-Host ""

Write-Host "Warming model and verifying GPU..." -ForegroundColor Yellow
$warmPayload = @{
    model = $modelName
    prompt = "{`"ok`":true}"
    stream = $false
    format = "json"
    options = @{
        num_predict = 16
        num_ctx = 1024
        temperature = 0
    }
} | ConvertTo-Json -Depth 5
Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/generate" -Method POST -Body $warmPayload -ContentType "application/json" -TimeoutSec 180 | Out-Null
$psOut = ollama ps
if ($psOut -match "100% CPU") {
    throw "Ollama is still on CPU. Aborting launch to avoid slow runtime."
}
Write-Host "GPU mode detected." -ForegroundColor Green
Write-Host ""

Write-Host "Starting ARIA runtime..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

python -m aria.main
