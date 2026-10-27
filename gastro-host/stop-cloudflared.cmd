@echo off
rem Stoppt den Cloudflare-Tunnel. Das Gastro-Fenster ruft diese Datei nicht auf.
taskkill /F /IM cloudflared.exe /T >nul 2>&1
