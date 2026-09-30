$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ProjectDir "server.pid"
$stopped = $false

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
    Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments -WorkingDirectory $ProjectDir
    exit 0
}

function Backup-BeforeStop {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/system/backup-all?tag=exit" -Method Post -TimeoutSec 5 | Out-Null
        Write-Host "Exit backup requested." -ForegroundColor Green
    } catch {
        Write-Host "Exit backup skipped (server not responding)." -ForegroundColor Yellow
    }
}

function Stop-InventoryProcess([int]$ProcessId) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if (-not $processInfo) { return $false }

    $commandLine = [string]$processInfo.CommandLine
    if ($commandLine -notlike "*launcher.py*" -or $commandLine -notlike "*$ProjectDir*") {
        return $false
    }

    Stop-Process -Id $ProcessId -Force
    return $true
}

# 강제 종료 전에 실행 중인 서버에 전체 DB 백업을 한 번 요청한다.
Backup-BeforeStop

if (Test-Path $PidFile) {
    $savedPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($savedPid -match '^\d+$') {
        $stopped = Stop-InventoryProcess ([int]$savedPid)
    }
}

# Also finds a server started before PID tracking was added.
if (-not $stopped) {
    $servers = Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            ([string]$_.CommandLine -like "*launcher.py*") -and
            ([string]$_.CommandLine -like "*$ProjectDir*")
        }
    foreach ($server in $servers) {
        Stop-Process -Id $server.ProcessId -Force
        $stopped = $true
    }
}

# Final fallback: identify the Python process that is actually listening on port 5000.
$listeners = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
    if (-not $processInfo) { continue }

    $name = [string]$processInfo.Name
    $commandLine = [string]$processInfo.CommandLine
    $executable = [string]$processInfo.ExecutablePath
    $projectPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    $projectPythonw = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
    $isProjectServer = ($name -in @("python.exe", "pythonw.exe")) -and (
        $commandLine -like "*launcher.py*" -or
        $executable -eq $projectPython -or
        $executable -eq $projectPythonw
    )

    if ($isProjectServer) {
        Stop-Process -Id $listener.OwningProcess -Force
        $stopped = $true
    }
}

Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
$stillListening = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue

if (-not $stillListening) {
    Write-Host "Server is OFF. Port 5000 is closed." -ForegroundColor Green
    Write-Host "A browser page may remain open, but it can no longer communicate with the server."
} elseif ($stopped) {
    Write-Host "A process was stopped, but port 5000 is still in use." -ForegroundColor Red
    exit 1
} else {
    Write-Host "Port 5000 is used by another program, so it was not stopped." -ForegroundColor Yellow
    exit 1
}
