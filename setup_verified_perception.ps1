#!/usr/bin/env pwsh
# Setup script for Verified Perception Layer

Write-Host "=== Setting up Verified Perception Layer ===" -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment exists
if (-not (Test-Path ".venv")) {
    Write-Host "Virtual environment not found. Creating..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Green
& .venv\Scripts\Activate.ps1

# Install/upgrade dependencies
Write-Host ""
Write-Host "Installing new dependencies..." -ForegroundColor Green
pip install --upgrade pip
pip install sentence-transformers uiautomation watchdog

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "New components installed:" -ForegroundColor Yellow
Write-Host "  - sentence-transformers (semantic deduplication)"
Write-Host "  - uiautomation (Windows UIA adapter)"
Write-Host "  - watchdog (file system monitoring)"
Write-Host ""
Write-Host "Configuration added to .env:" -ForegroundColor Yellow
Write-Host "  - ENABLE_VERIFIED_PERCEPTION=true"
Write-Host "  - RESPONSE_MAX_WORDS=12"
Write-Host "  - SEMANTIC_DEDUP_SIMILARITY_THRESHOLD=0.85"
Write-Host ""
Write-Host "To test the perception pipeline:" -ForegroundColor Green
Write-Host "  python test_verified_perception.py"
Write-Host ""
Write-Host "To run ARIA with verified perception:" -ForegroundColor Green
Write-Host "  python -m screensense.app"
Write-Host ""
