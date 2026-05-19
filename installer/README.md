# Gastro-System Windows Setup

## Setup-EXE erstellen

Voraussetzungen auf dem Build-PC:

- Python 3.10+
- Internet (für `pip install pyinstaller`)

```powershell
cd C:\Applikationen\Gastro-System\installer
powershell -ExecutionPolicy Bypass -File .\build-setup.ps1
```

Ergebnis:

- `installer\dist\setup.exe` (genau eine Datei – hier starten oder kopieren)

## Setup ohne EXE (Entwicklung)

```powershell
python installer\gastro_setup_wizard.py
```

Konfiguriert das Repo in-place, wenn Quell- und Zielordner identisch sind.

## Assistent – Schritte

Beim Start erscheint die **Windows-UAC-Abfrage (Administrator)** – bitte bestätigen.

1. **Willkommen** – Kurzinfo, Status von Python/cloudflared
2. **Installationsordner** – z. B. `C:\Applikationen\Gastro-System`
3. **LAN-IP** – ermitteln, mit „IP prüfen“ validieren (Pflicht)
4. **Cloudflare** – optional; Tunnel-Daten; cloudflared kann mitinstalliert werden; Anleitung im Browser
5. **Installation** – Zusammenfassung; optional Python installieren, Desktop-Link, **Windows-Aufgaben** (Autostart nach Anmeldung – in Klartext erklärt)

### Automatische Installation

- **Python 3.12** – per winget oder Download von python.org (Haken auf letzter Seite)
- **cloudflared** – nur bei aktivem Tunnel; per winget oder Download nach `Program Files\cloudflared`

## Nach der Installation

- Automatisch: **`data\Gastro-System-Nutzungsanleitung.html`** (URLs, Seitenübersicht, Bedienung) – wird im Browser geöffnet
- Control Panel: `gastro-host\run-control-panel.cmd` oder Desktop-Link **Gastro-System**
- Autostart (optional): Setup-Haken oder manuell als Admin:

```powershell
powershell -ExecutionPolicy Bypass -File gastro-host\register-gastro-tasks.ps1 -InstallRoot "C:\Applikationen\Gastro-System" -CloudflareEnabled
```

## Cloudflare

Siehe `installer/resources/cloudflare_anleitung.html`.
