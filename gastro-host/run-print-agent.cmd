@echo off
cd /d "%~dp0"
set "GASTRO_PRINT_PORT=9109"
set "GASTRO_PRINT_BIND=0.0.0.0"
REM optional: set GASTRO_PRINTER_NAME=HP_A798
if exist "%~dp0..\venv\Scripts\python.exe" (
  "%~dp0..\venv\Scripts\python.exe" "%~dp0print_agent.py"
) else (
  python "%~dp0print_agent.py"
)
