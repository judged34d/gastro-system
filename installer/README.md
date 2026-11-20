# Gastro-System Windows Setup (Offline-fähig)

## Setup-EXE erstellen (Build-PC mit Internet)

```powershell
cd C:\Applikationen\Gastro-System\installer
powershell -ExecutionPolicy Bypass -File .\build-setup.ps1
```

Das Skript:

1. Lädt bei Bedarf Offline-Bundle (`fetch-offline-deps.ps1`: Python-Installer + Wheels + cloudflared)
2. Baut `dist\setup.exe` (alles eingebettet – Ziel-PC braucht **kein** Internet)
3. Legt `dist\USB-Stick\` an (`setup.exe`, Anleitung, LIESMICH.txt)

## Auf den USB-Stick kopieren

Inhalt von `installer\dist\USB-Stick\` komplett auf den Stick kopieren.

## Ziel-PC (ohne Internet)

1. `setup.exe` starten → UAC mit **Ja** bestätigen
2. Cloudflare für Offline **deaktivieren**
3. LAN-IP prüfen, Ordner wählen, installieren
4. Desktop-Link **Gastro-System** → **Gastro-System starten**
5. Tablets: `http://<LAN-IP>:8081/`

## Was eingebettet ist

| Komponente | Zweck |
|------------|--------|
| Programmdateien | Backend, Frontend, Control Panel |
| Python 3.12 Installer | Laufzeit inkl. tkinter |
| wheels/ | Flask, flask-cors (offline pip) |
| cloudflared.exe | optional Online-Tunnel |
| Anleitung | Offline-Event-Einrichtung |

**Nicht nötig:** .NET, Node, Java, Internet auf dem Ziel-PC.

## Setup ohne EXE (Entwicklung)

```powershell
# Offline-Bundle einmal holen
powershell -ExecutionPolicy Bypass -File installer\fetch-offline-deps.ps1
python installer\gastro_setup_wizard.py
```
