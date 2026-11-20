@echo off
setlocal
cd /d "%~dp0"
call "%~dp0config.cmd" 2>nul

rem Niemals pythonw aus dem PATH (Inkscape!) – nur Gastro-venv
set "PYW=%GASTRO_ROOT%\venv\Scripts\pythonw.exe"
set "PY=%GASTRO_ROOT%\venv\Scripts\python.exe"
if not exist "%PYW%" if exist "%PY%" set "PYW=%PY%"

if not exist "%PYW%" (
  echo.
  echo FEHLER: Gastro-venv nicht gefunden.
  echo Erwartet: %GASTRO_ROOT%\venv\Scripts\pythonw.exe
  echo Bitte setup.exe erneut als Administrator ausfuehren.
  echo.
  pause
  exit /b 1
)

start "" "%PYW%" "%~dp0control_panel.py"
exit /b 0
