@echo off
:: Gastro-System deinstallieren (Admin)
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Administratorrechte erforderlich …
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
echo.
pause
