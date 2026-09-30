$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Stop and start both need administrator rights; elevate once for the whole restart.
if (-not (Test-Administrator)) {
    Write-Host "Requesting administrator permission to restart the server..."
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
    Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments -WorkingDirectory $ProjectDir
    exit 0
}

Write-Host "`n==> Stopping the server" -ForegroundColor Cyan
powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectDir "stop_server.ps1")

Write-Host "`n==> Starting the server" -ForegroundColor Cyan
powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectDir "setup_and_start.ps1")
