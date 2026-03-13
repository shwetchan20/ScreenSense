param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [Parameter(Mandatory = $true)][string]$Region,
    [string]$ServiceName = "screensense-backend",
    [string]$Repository = "screensense",
    [string]$ImageName = "screensense-backend"
)

$ErrorActionPreference = "Stop"

$ImageUri = "$Region-docker.pkg.dev/$ProjectId/$Repository/$ImageName:latest"

Write-Host "Building backend image: $ImageUri"
gcloud builds submit --project $ProjectId --tag $ImageUri -f Dockerfile.backend .

Write-Host "Deploying Cloud Run service: $ServiceName"
gcloud run deploy $ServiceName `
  --project $ProjectId `
  --region $Region `
  --image $ImageUri `
  --platform managed `
  --allow-unauthenticated `
  --set-env-vars GEMINI_MODEL=gemini-2.5-flash `
  --set-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest,BACKEND_AUTH_TOKEN=BACKEND_AUTH_TOKEN:latest

Write-Host "Deployment command completed."

