param(
    [string]$LogPath,
    [switch]$FirewallOnly
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$FirewallRuleName = "Inventory App TCP 5000"
$Port = 5000
$HttpsFirewallRuleName = "Inventory App TCP 5443"
$HttpsPort = 5443
$MinimumPythonVersion = "3.10"
$PythonVersionCheck = "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
Set-Location $ProjectDir

if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $ProjectDir "install-start.log"
}
$ServerLogPath = Join-Path $ProjectDir "server.log"

function Write-LogLine([string]$Message) {
    try {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $LogPath -Value "[$stamp] $Message" -Encoding UTF8
    } catch { }
}

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
    Write-LogLine "==> $Message"
}

function Write-Warn([string]$Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
    Write-LogLine "[WARN] $Message"
}

function Write-LoggedOutput($Output) {
    foreach ($line in $Output) {
        $text = [string]$line
        if ($text.Length -gt 0) {
            Write-Host $text
            Write-LogLine $text
        }
    }
}

function Invoke-NativeLogged([scriptblock]$Command) {
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $Command 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPreference
    }
    Write-LoggedOutput $output
    return $exitCode
}

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-PythonSpec([string]$Spec, [string[]]$Arguments) {
    $parts = $Spec -split "\|", 2
    if ($parts.Count -eq 2) {
        & $parts[0] $parts[1] @Arguments
    } else {
        & $Spec @Arguments
    }
}

function Test-SupportedPythonSpec([string]$Spec) {
    try {
        Invoke-PythonSpec $Spec @("-c", $PythonVersionCheck) 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Get-PythonVersionText([string]$Spec) {
    try {
        $version = Invoke-PythonSpec $Spec @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')") 2>$null |
            Select-Object -Last 1
        if ($LASTEXITCODE -eq 0 -and $version) { return [string]$version }
    } catch { }
    return "unknown"
}

function Find-Python {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python -and (Test-SupportedPythonSpec $python.Source)) {
        return $python.Source
    }

    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($versionArg in @("-3", "-3.14", "-3.13", "-3.12", "-3.11", "-3.10")) {
            $spec = "$($py.Source)|$versionArg"
            if (Test-SupportedPythonSpec $spec) { return $spec }
        }
    }

    $localPythons = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    foreach ($candidate in $localPythons) {
        if (Test-SupportedPythonSpec $candidate.FullName) { return $candidate.FullName }
    }

    return $null
}

function Install-Python312 {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Python $MinimumPythonVersion or newer was not found, and winget is not available. Install Python, then run ONE_CLICK_START.bat again."
    }

    Write-Step "Installing Python 3.12"
    $exitCode = Invoke-NativeLogged { & $winget.Source install --id Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements }
    if ($exitCode -ne 0) {
        throw "Automatic Python 3.12 installation failed. See $LogPath."
    }
}

function Ensure-FirewallRules {
    Write-Step "Configuring Windows Firewall for other PCs"
    if (-not (Test-Administrator)) {
        Write-Warn "Firewall registration needs administrator permission. Asking Windows once."
        $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`" -FirewallOnly -LogPath `"$LogPath`""
        try {
            Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments -WorkingDirectory $ProjectDir -Wait
        } catch {
            Write-Warn "Firewall rule was skipped. Localhost will work, but other PCs may be blocked."
        }
        return
    }

    try {
        $existingRule = Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue
        if (-not $existingRule) {
            New-NetFirewallRule -DisplayName $FirewallRuleName -Direction Inbound -Action Allow `
                -Protocol TCP -LocalPort $Port -Profile Any -RemoteAddress LocalSubnet | Out-Null
            Write-LogLine "Created firewall rule $FirewallRuleName."
        }

        $existingHttpsRule = Get-NetFirewallRule -DisplayName $HttpsFirewallRuleName -ErrorAction SilentlyContinue
        if (-not $existingHttpsRule) {
            New-NetFirewallRule -DisplayName $HttpsFirewallRuleName -Direction Inbound -Action Allow `
                -Protocol TCP -LocalPort $HttpsPort -Profile Any -RemoteAddress LocalSubnet | Out-Null
            Write-LogLine "Created firewall rule $HttpsFirewallRuleName."
        }
    } catch {
        Write-Warn "Firewall setup failed: $($_.Exception.Message)"
        Write-Warn "The server can still run on this PC. Other PCs may need firewall permission later."
    }
}

function Test-InventoryServer {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Stop-ExistingInventoryServer {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) { return }

    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $commandLine = [string]$processInfo.CommandLine
    $executable = [string]$processInfo.ExecutablePath
    $projectPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    $projectPythonw = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
    $isProjectServer = (
        ($commandLine.Contains("launcher.py") -and $commandLine.Contains($ProjectDir)) -or
        ($executable -eq $projectPython) -or
        ($executable -eq $projectPythonw)
    )

    if (-not $isProjectServer) {
        throw "Port $Port is already used by another program. Close that program and try again."
    }

    Write-Host "An older inventory server is running. Restarting it to apply the latest files..."
    Write-LogLine "Stopping existing inventory server on port $Port."
    Stop-Process -Id $listener.OwningProcess -Force
    Start-Sleep -Milliseconds 700
    Remove-Item (Join-Path $ProjectDir "server.pid") -Force -ErrorAction SilentlyContinue
}

function Wait-ForServer {
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-InventoryServer) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

if ($FirewallOnly) {
    Ensure-FirewallRules
    exit 0
}

try {
    New-Item -ItemType File -Path $LogPath -Force | Out-Null
    Write-LogLine "Starting one-click setup in $ProjectDir."
    Write-LogLine "Required Python version: $MinimumPythonVersion or newer."

    Write-Step "Checking Python"
    $venvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    $venvReady = $false
    if (Test-Path $venvPython) {
        try {
            & $venvPython -c $PythonVersionCheck 2>$null
            $venvReady = ($LASTEXITCODE -eq 0)
        } catch { }
    }

    if (-not $venvReady -and (Test-Path (Join-Path $ProjectDir ".venv"))) {
        $backupName = ".venv.broken.$(Get-Date -Format 'yyyyMMddHHmmss')"
        Write-Warn "The existing .venv is not usable on this PC. Saving it as $backupName."
        Move-Item (Join-Path $ProjectDir ".venv") (Join-Path $ProjectDir $backupName)
    }

    $python = if ($venvReady) { $venvPython } else { Find-Python }
    if (-not $python) {
        Install-Python312
        $python = Find-Python
        if (-not $python) {
            throw "Python was installed but is not visible yet. Sign out of Windows, sign back in, then run ONE_CLICK_START.bat again."
        }
    }

    if ($venvReady) {
        Write-LogLine "Using existing project Python environment."
    } else {
        Write-LogLine "Using detected Python $((Get-PythonVersionText $python)) from $python."
    }

    if (-not (Test-Path $venvPython)) {
        Write-Step "Creating the private Python environment"
        Invoke-PythonSpec $python @("-m", "venv", ".venv")
        if ($LASTEXITCODE -ne 0) { throw "Failed to create the Python environment." }
    }

    Write-Step "Installing/updating required packages"
    $pipExitCode = Invoke-NativeLogged { & $venvPython -m pip install --no-cache-dir --disable-pip-version-check -r "requirements.txt" }
    if ($pipExitCode -ne 0) {
        throw "Failed to install the required packages. See $LogPath."
    }

    Ensure-FirewallRules

    Write-Step "Starting server"
    Stop-ExistingInventoryServer
    Add-Content -Path $ServerLogPath -Value "`n[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Requested server start from setup script." -Encoding UTF8
    $vbs = Join-Path $ProjectDir "start_hidden.vbs"
    Start-Process wscript.exe -ArgumentList "`"$vbs`"" -WorkingDirectory $ProjectDir

    if (-not (Wait-ForServer)) {
        Write-Warn "Server did not respond after startup."
        if (Test-Path $ServerLogPath) {
            Write-Host "`nLast server log lines:" -ForegroundColor Yellow
            Get-Content $ServerLogPath -Tail 40
        }
        throw "Server startup failed. See $ServerLogPath."
    }

    $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object -ExpandProperty IPAddress -Unique

    Write-Host "`nServer is running." -ForegroundColor Green
    Write-Host "A PC:       http://localhost:$Port"
    foreach ($address in $addresses) {
        Write-Host "B/C/D PC:   http://${address}:$Port" -ForegroundColor Yellow
    }
    foreach ($address in $addresses) {
        Write-Host "Mobile:     https://${address}:$HttpsPort  (camera scan; accept the security warning once)" -ForegroundColor Green
    }
    Write-Host "`nConnect B/C/D to the same office network as A, then open one of the addresses above."
    Write-Host "First login: admin / admin (change the password immediately)."
    Write-Host "Install log: $LogPath"
    Write-Host "Server log:  $ServerLogPath"
    Write-Host "This window will close automatically in 12 seconds."
    Write-LogLine "Server startup completed."
    Start-Sleep -Seconds 12
} catch {
    Write-LogLine "[ERROR] $($_.Exception.Message)"
    Write-Host "`n[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Install log: $LogPath"
    Write-Host "Server log:  $ServerLogPath"
    exit 1
}
