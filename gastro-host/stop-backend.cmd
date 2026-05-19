@echo off
call "%~dp0config.cmd"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%GASTRO_BACKEND_PORT%" ^| findstr /i "ABH LISTENING"') do taskkill /F /PID %%a /T >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -EA SilentlyContinue | Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -like '*Gastro-System*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }"
