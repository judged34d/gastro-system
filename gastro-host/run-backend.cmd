@echo off
call "%~dp0config.cmd"
if not exist "%GASTRO_PYTHON%" exit /b 1
netstat -ano | findstr ":%GASTRO_BACKEND_PORT% .*ABH" >nul 2>&1 && exit /b 0
start "" /B cmd /c "cd /d "%GASTRO_ROOT%\backend" && set GASTRO_DB_PATH=%GASTRO_DB_PATH% && set GASTRO_BACKEND_PORT=%GASTRO_BACKEND_PORT% && set PYTHONUNBUFFERED=1 && "%GASTRO_PYTHON%" main.py >> "%GASTRO_ROOT%\data\backend.log" 2>&1"
