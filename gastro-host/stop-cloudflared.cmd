@echo off
rem Gemeinsamer Tunnel für app.mpbin.de, api.mpbin.de und design.mpbin.de.
rem Das Gastro-Fenster stoppt diesen Tunnel nicht mehr. Das Leisten-Symbol schon.
taskkill /F /IM cloudflared.exe /T >nul 2>&1
