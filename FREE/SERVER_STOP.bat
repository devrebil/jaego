@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_server.ps1"
timeout /t 3 /nobreak >nul

