@echo off
cd /d "%~dp0"
if exist "C:\Applikationen\Gastro-System\venv\Scripts\pythonw.exe" (
    start "" "C:\Applikationen\Gastro-System\venv\Scripts\pythonw.exe" "%~dp0control_panel.py"
) else (
    start "" pythonw "%~dp0control_panel.py"
)
