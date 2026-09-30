@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem PowerShell script handles Python, packages, Windows Firewall, and startup.
set "INSTALL_LOG=%~dp0install-start.log"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_and_start.ps1" -LogPath "%INSTALL_LOG%"

if errorlevel 1 (
    echo.
    echo [ERROR] Setup or startup failed. See the message above.
    echo Log file: "%INSTALL_LOG%"
    if exist "%INSTALL_LOG%" (
        echo.
        echo --- Last install log lines ---
        powershell.exe -NoProfile -Command "Get-Content -LiteralPath '%INSTALL_LOG%' -Tail 80"
    )
    pause
)
