param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8090
)

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Error "Virtual environment not found at .\.venv. Create/activate it first."
    exit 1
}

& .\.venv\Scripts\python.exe -m uvicorn screensense.ui.webapp:app --host $BindHost --port $Port
