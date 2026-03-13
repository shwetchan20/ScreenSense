param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 8080
)

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Error "Virtual environment not found at .\.venv. Create/activate it first."
    exit 1
}

if (-not $env:GEMINI_API_KEY -or $env:GEMINI_API_KEY.Trim() -eq "") {
    Write-Host "GEMINI_API_KEY is not set in current shell."
    Write-Host "Set it first: `$env:GEMINI_API_KEY='YOUR_KEY'"
    exit 1
}

& .\.venv\Scripts\python.exe -m uvicorn screensense.backend.app:app --host $Host --port $Port

