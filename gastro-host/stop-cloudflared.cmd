@echo off
rem Stoppt nur den Tunnel dieses Gastro-Systems.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='cloudflared.exe'\" | Where-Object { $_.CommandLine -like '*Gastro-System\cloudflared\config.yml*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
exit /b 0
