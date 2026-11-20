@echo off
call "%~dp0config.cmd"
call "%~dp0run-backend.cmd"
call "%~dp0run-frontend.cmd"
:: Tunnel nur wenn aktiviert – Offline/Fritzbox: GASTRO_CLOUDFLARED_ENABLED=0 oder Control Panel ohne Tunnel
call "%~dp0run-cloudflared.cmd"
timeout /t 3 /nobreak >nul
echo.
echo Lokal:
echo   Backend  : http://127.0.0.1:%GASTRO_BACKEND_PORT%/health
echo   Frontend : http://127.0.0.1:%GASTRO_FRONTEND_PORT%/
echo.
echo LAN (Tablets, gleiches WLAN):
echo   Frontend : http://%GASTRO_LAN_IP%:%GASTRO_FRONTEND_PORT%/
echo   Backend  : http://%GASTRO_LAN_IP%:%GASTRO_BACKEND_PORT%/health
if "%GASTRO_CLOUDFLARED_ENABLED%"=="0" (
    echo.
    echo Cloudflare: deaktiviert ^(Offline-Modus^)
) else (
    echo.
    echo Cloudflare: aktiviert – braucht Internet. Offline: nur Backend+Frontend nutzen.
)
echo.
pause
