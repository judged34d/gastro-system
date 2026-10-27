@echo off
call "%~dp0config.cmd"
set "CF_LOG=%GASTRO_ROOT%\data\cloudflared.log"
if not exist "%GASTRO_ROOT%\data" mkdir "%GASTRO_ROOT%\data" >nul 2>&1

if "%GASTRO_CLOUDFLARED_ENABLED%"=="0" (
    >>"%CF_LOG%" echo [%date% %time%] Cloudflared nicht gestartet: GASTRO_CLOUDFLARED_ENABLED=0 in gastro-host\config.cmd
    exit /b 0
)
if not exist "%GASTRO_CLOUDFLARED_EXE%" (
    >>"%CF_LOG%" echo [%date% %time%] Cloudflared nicht gestartet: cloudflared.exe fehlt unter "%GASTRO_CLOUDFLARED_EXE%"
    exit /b 1
)
if not exist "%GASTRO_CLOUDFLARED_CFG%" (
    >>"%CF_LOG%" echo [%date% %time%] Cloudflared nicht gestartet: config fehlt "%GASTRO_CLOUDFLARED_CFG%"
    exit /b 1
)
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"Name='cloudflared.exe'\" | Where-Object { $_.CommandLine -like '*Gastro-System\cloudflared\config.yml*' }) { exit 0 } else { exit 1 }"
if not errorlevel 1 exit /b 0

>>"%CF_LOG%" echo.
>>"%CF_LOG%" echo ===== [%date% %time%] cloudflared start =====
start "GastroCloudflared" /B "%GASTRO_CLOUDFLARED_EXE%" tunnel --config "%GASTRO_CLOUDFLARED_CFG%" --metrics 127.0.0.1:20241 run >>"%CF_LOG%" 2>&1
exit /b 0
