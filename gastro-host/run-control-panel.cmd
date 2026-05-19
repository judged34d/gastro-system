@echo off
cd /d "%~dp0"
call "%~dp0config.cmd" 2>nul
set "PYW=%GASTRO_ROOT%\venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw"
start "" "%PYW%" "%~dp0control_panel.py"
