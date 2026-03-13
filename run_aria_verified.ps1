#!/usr/bin/env pwsh
# Run ARIA with Verified Perception

Write-Host "=== Starting ARIA with Verified Perception ===" -ForegroundColor Cyan
Write-Host ""

# Check if Ollama is running
Write-Host "Checking Ollama status..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -Method GET -TimeoutSec 2 -ErrorAction Stop
    Write-Host "✓ Ollama is running" -ForegroundColor Green
} catch {
    Write-Host "✗ Ollama is not running!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please start Ollama first:" -ForegroundColor Yellow
    Write-Host "  ollama run llama3.2:3b" -ForegroundColor White
    Write-Host ""
    exit 1
}

# Check if llama3.2:3b is available
Write-Host "Checking llama3.2:3b model..." -ForegroundColor Yellow
$models = (Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -Method GET).Content | ConvertFrom-Json
$hasLlama = $models.models | Where-Object { $_.name -like "llama3.2:3b*" }

if (-not $hasLlama) {
    Write-Host "✗ llama3.2:3b not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please pull the model first:" -ForegroundColor Yellow
    Write-Host "  ollama pull llama3.2:3b" -ForegroundColor White
    Write-Host ""
    exit 1
}

Write-Host "✓ llama3.2:3b is available" -ForegroundColor Green
Write-Host ""

# Check verified perception settings
Write-Host "Verified Perception Configuration:" -ForegroundColor Cyan
Write-Host "  - OmniParser: YOLOv8n (CPU)" -ForegroundColor White
Write-Host "  - Windows UIA: Enabled (500ms cache)" -ForegroundColor White
Write-Host "  - Cross-Modal Verification: Enabled" -ForegroundColor White
Write-Host "  - Passive Signals: Clipboard + Browser URL" -ForegroundColor White
Write-Host "  - Semantic Dedup: Enabled (0.85 threshold)" -ForegroundColor White
Write-Host "  - Response Limit: 12 words" -ForegroundColor White
Write-Host ""

# Start ARIA
Write-Host "Starting ARIA..." -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

python -m screensense.app
