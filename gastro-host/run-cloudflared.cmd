@echo off
call "%~dp0config.cmd"
if "%GASTRO_CLOUDFLARED_ENABLED%"=="0" exit /b 0
if not exist "%GASTRO_CLOUDFLARED_EXE%" exit /b 1
if not exist "%GASTRO_CLOUDFLARED_CFG%" exit /b 1
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>nul | find /I "cloudflared.exe" >nul && exit /b 0
start "" /B cmd /c ""%GASTRO_CLOUDFLARED_EXE%" tunnel --config "%GASTRO_CLOUDFLARED_CFG%" run >> "%GASTRO_ROOT%\data\cloudflared.log" 2>&1"
