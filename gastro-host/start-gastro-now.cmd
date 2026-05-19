@echo off
call "%~dp0run-backend.cmd"
call "%~dp0run-frontend.cmd"
call "%~dp0run-cloudflared.cmd"
timeout /t 3 /nobreak >nul
echo Backend  : http://127.0.0.1:8000/health
echo Frontend : http://127.0.0.1:8081/
pause
