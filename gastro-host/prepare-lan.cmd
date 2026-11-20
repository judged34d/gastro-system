@echo off
:: LAN-IP + Firewall fuer Offline-/Fritzbox-Betrieb
:: Beispiele:
::   prepare-lan.cmd
::   prepare-lan.cmd -DisableCloudflare
::   prepare-lan.cmd -LanIp 192.168.178.20
::   prepare-lan.cmd -LanIp 192.168.178.20 -DisableCloudflare
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare-lan.ps1" %*
echo.
pause
