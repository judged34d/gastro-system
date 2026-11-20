# Offline-Bundle

Wird von `fetch-offline-deps.ps1` befüllt und in `setup.exe` eingebettet.

Enthalten nach dem Fetch:

- `python-3.12.10-amd64.exe` – Python-Vollinstaller (inkl. Tcl/Tk)
- `wheels\` – Flask + Abhängigkeiten für `pip install --no-index`
- `cloudflared.exe` – optional für Tunnel ohne Download

Diese Dateien sind groß und liegen typischerweise **nicht** in Git (siehe `.gitignore`).
