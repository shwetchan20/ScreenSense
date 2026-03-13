param(
  [string]$TaskName = "ScreenSense-Agent",
  [string]$ProjectRoot = "",
  [string]$PowerShellExe = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
  $ProjectRoot = (Get-Location).Path
}

$runnerScript = Join-Path $ProjectRoot "scripts\start_agent_background.ps1"
if (-not (Test-Path $runnerScript)) {
  throw "Runner script not found: $runnerScript"
}

$actionArgs = "-ExecutionPolicy Bypass -File `"$runnerScript`""
$action = New-ScheduledTaskAction -Execute $PowerShellExe -Argument $actionArgs -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Principal $principal `
  -Settings $settings `
  -Force | Out-Null

Write-Host "[autostart] Task '$TaskName' registered."
Write-Host "[autostart] It will launch ScreenSense at user logon."
