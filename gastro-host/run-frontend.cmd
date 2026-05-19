@echo off
call "%~dp0config.cmd"
if not exist "%GASTRO_PYTHON%" exit /b 1
netstat -ano | findstr ":%GASTRO_FRONTEND_PORT% .*ABH" >nul 2>&1 && exit /b 0
start "" /B cmd /c "cd /d "%GASTRO_ROOT%" && set FRONTEND_PORT=%GASTRO_FRONTEND_PORT% && set PYTHONUNBUFFERED=1 && "%GASTRO_PYTHON%" deploy\frontend_server.py >> "%GASTRO_ROOT%\data\frontend.log" 2>&1"
