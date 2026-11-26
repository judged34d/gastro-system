@echo off
:: Beendet haengende Gastro-Prozesse und deaktiviert alte geplante Tasks (C:\srv).
:: Als Administrator ausfuehren.
setlocal
echo === Gastro Force-Stop (Admin) ===

schtasks /End /TN "GastroBackend" >nul 2>&1
schtasks /End /TN "GastroFrontend" >nul 2>&1
schtasks /End /TN "GastroCloudflared" >nul 2>&1
schtasks /Change /TN "GastroBackend" /DISABLE >nul 2>&1
schtasks /Change /TN "GastroFrontend" /DISABLE >nul 2>&1
schtasks /Change /TN "GastroCloudflared" /DISABLE >nul 2>&1

for %%P in (8000 8081 20241) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P" ^| findstr /i "ABH LISTENING"') do (
    echo Kill PID %%a on port %%P
    taskkill /F /PID %%a /T >nul 2>&1
  )
)

powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process -EA SilentlyContinue | Where-Object { $_.Name -in @('python.exe','pythonw.exe','cloudflared.exe') -and ( $_.CommandLine -match 'Gastro-System|gastro-host|\\srv\\gastro|frontend_server|main\.py|cloudflared' -or -not $_.CommandLine ) } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -EA Stop; Write-Host ('killed ' + $_.ProcessId) } catch { Write-Host ('fail ' + $_.ProcessId + ': ' + $_.Exception.Message) } }"

echo.
echo Ports danach:
netstat -ano | findstr ":8000 :8081" | findstr /i "ABH LISTENING"
echo.
echo Fertig. Fenster kann geschlossen werden.
pause
