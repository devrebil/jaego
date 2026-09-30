@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem Stops the running inventory server and starts it again with the latest files.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_server.ps1"

if errorlevel 1 (
    echo.
    echo [ERROR] Restart failed. See the message above.
    pause
)
