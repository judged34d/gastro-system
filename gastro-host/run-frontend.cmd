@echo off
REM Only manual start (Control Panel / Tray / start-gastro-now) - ignore login tasks
if /I not "%GASTRO_MANUAL_START%"=="1" exit /b 0
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0config.cmd"
if not defined GASTRO_ROOT set "GASTRO_ROOT=%~dp0.."
if not exist "%GASTRO_ROOT%\data" mkdir "%GASTRO_ROOT%\data" >nul 2>&1

set "PY=%GASTRO_ROOT%\venv\Scripts\python.exe"
if not exist "%PY%" (
  >>"%GASTRO_ROOT%\data\startup.log" echo [%date% %time%] Frontend: venv fehlt %PY%
  exit /b 1
)

"%PY%" "%~dp0launch_service.py" frontend
exit /b %ERRORLEVEL%
