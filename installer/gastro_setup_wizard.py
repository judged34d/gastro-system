#!/usr/bin/env python3
"""
Gastro-System Windows Setup-Assistent.
Kann als Skript oder als PyInstaller-EXE (mit eingebettetem payload/) laufen.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

_INSTALLER_DIR = Path(__file__).resolve().parent
if str(_INSTALLER_DIR) not in sys.path:
    sys.path.insert(0, str(_INSTALLER_DIR))

from install_handbook import write_install_handbook  # noqa: E402
from setup_prereqs import (  # noqa: E402
    PY_TARGET_EXE,
    cloudflared_version_label,
    find_cloudflared,
    find_python,
    install_cloudflared,
    install_python,
    install_python_packages,
    offline_ready_label,
    python_version_label,
    request_admin_at_startup,
    require_offline_bundle,
    wait_for_usable_python,
    _is_usable_python,
)

APP_TITLE = "Gastro-System Setup"
STEP_TITLES = (
    "Willkommen",
    "Installationsordner",
    "Netzwerk (LAN-IP)",
    "Cloudflare Tunnel",
    "Installation abschließen",
)
DEFAULT_INSTALL = r"C:\Applikationen\Gastro-System"
DEFAULT_CF_EXE = r"C:\Program Files\cloudflared\cloudflared.exe"

SKIP_COPY = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "installer/staging",
    "installer/build",
    "installer/dist",
    "GastroSystemControl.exe_extracted",
}
SKIP_COPY_NAMES = {".git", "venv", ".venv", "__pycache__"}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    """Quellordner: payload im Bundle oder Repo-Wurzel."""
    payload = app_dir() / "payload"
    if payload.is_dir() and (payload / "backend").is_dir():
        return payload
    return Path(__file__).resolve().parent.parent


def guide_path() -> Path:
    p = app_dir() / "resources" / "cloudflare_anleitung.html"
    if p.is_file():
        return p
    return Path(__file__).resolve().parent / "resources" / "cloudflare_anleitung.html"


def list_lan_ips() -> list[str]:
    found: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and ip not in found:
                found.append(ip)
    except OSError:
        pass
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or ip in found:
                continue
            found.append(ip)
    except OSError:
        pass
    # ipconfig fallback (Windows)
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for m in re.finditer(
                r"IPv4[^:]*:\s*(\d+\.\d+\.\d+\.\d+)", out.stdout or "", re.I
            ):
                ip = m.group(1)
                if not ip.startswith("127.") and ip not in found:
                    found.append(ip)
        except (OSError, subprocess.SubprocessError):
            pass
    return found or ["127.0.0.1"]


def verify_ip(ip: str) -> tuple[bool, str]:
    ip = (ip or "").strip()
    if not ip:
        return False, "Keine IP gewählt."
    if ip.startswith("127."):
        return True, "Loopback – nur Zugriff auf diesem PC."
    if ip.startswith("169.254."):
        return False, "Link-Local (APIPA) – kein gültiges LAN."
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((ip, 0))
        return (
            True,
            f"OK – Frontend: http://{ip}:8081  |  API: http://{ip}:8000/health",
        )
    except OSError as exc:
        return False, f"Interface nicht nutzbar: {exc}"


def read_tunnel_id(credentials: Path) -> str:
    data = json.loads(credentials.read_text(encoding="utf-8"))
    tid = (data.get("TunnelID") or data.get("tunnel_id") or "").strip()
    if not tid:
        raise ValueError("TunnelID fehlt in der Credentials-JSON.")
    return tid


def should_skip_copy(rel: Path) -> bool:
    parts = rel.parts
    if parts and parts[0] in SKIP_COPY_NAMES:
        return True
    if "data" in parts and rel.name.endswith((".db", ".log")):
        return True
    return False


def copy_tree(src: Path, dst: Path, log: callable) -> None:
    """Kopiert Payload. Kein messagebox hier – laeuft im Worker-Thread."""
    if src.resolve() == dst.resolve():
        log("Quelle = Ziel – Dateien werden nur konfiguriert.\n")
        return
    if dst.exists():
        log(f"Zielordner existiert – Dateien werden aktualisiert: {dst}\n")
    for root, dirs, files in os.walk(src):
        rel_root = Path(root).relative_to(src)
        dirs[:] = [
            d
            for d in dirs
            if d not in SKIP_COPY_NAMES and not should_skip_copy(rel_root / d)
        ]
        dest_dir = dst / rel_root
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            rel = rel_root / name
            if should_skip_copy(rel):
                continue
            s = Path(root) / name
            t = dest_dir / name
            shutil.copy2(s, t)
    log(f"Dateien kopiert nach {dst}\n")


def write_config_cmd(
    root: Path,
    lan_ip: str,
    cf_enabled: bool,
    cf_exe: str,
) -> None:
    host = root / "gastro-host" / "config.cmd"
    root_s = str(root.resolve())
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = str((data_dir / "database.db").resolve())
    venv_py = str((root / "venv" / "Scripts" / "python.exe").resolve())
    cf_cfg = str((root / "cloudflared" / "config.yml").resolve())
    # Absolute Pfade – kein %GASTRO_ROOT%-Expand noetig (fremd-PCs / Start ohne config.cmd-call)
    lines = [
        "@echo off",
        f'set "GASTRO_ROOT={root_s}"',
        f'set "GASTRO_DB_PATH={db_path}"',
        'set "GASTRO_BACKEND_PORT=8000"',
        'set "GASTRO_FRONTEND_PORT=8081"',
        f'set "GASTRO_PYTHON={venv_py}"',
        f'set "GASTRO_LAN_IP={lan_ip}"',
        f'set "GASTRO_CLOUDFLARED_ENABLED={"1" if cf_enabled else "0"}"',
        f'set "GASTRO_CLOUDFLARED_EXE={cf_exe}"',
        f'set "GASTRO_CLOUDFLARED_CFG={cf_cfg}"',
        "",
    ]
    host.parent.mkdir(parents=True, exist_ok=True)
    host.write_text("\n".join(lines), encoding="ascii", errors="replace", newline="\r\n")


def write_cloudflared_config(
    root: Path,
    tunnel_name: str,
    credentials_dest: Path,
    app_host: str,
    api_host: str,
) -> None:
    cfg = root / "cloudflared" / "config.yml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cred = credentials_dest.as_posix().replace("\\", "/")
    text = (
        f"tunnel: {tunnel_name}\n"
        f"credentials-file: {cred}\n\n"
        "ingress:\n"
        f"  - hostname: {app_host.strip()}\n"
        "    service: http://127.0.0.1:8081\n"
        f"  - hostname: {api_host.strip()}\n"
        "    service: http://127.0.0.1:8000\n"
        "  - service: http_status:404\n"
    )
    cfg.write_text(text, encoding="utf-8")


def write_host_json(root: Path, payload: dict) -> None:
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "host-config.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def desktop_dir() -> Path:
    userprofile = Path(os.environ.get("USERPROFILE", Path.home()))
    for name in ("Desktop", "Schreibtisch"):
        p = userprofile / name
        if p.is_dir():
            return p
    return userprofile / "Desktop"


def _create_shortcut(lnk: Path, target: Path, workdir: Path, description: str, log: callable) -> None:
    if sys.platform != "win32":
        return
    lnk.parent.mkdir(parents=True, exist_ok=True)
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut({json.dumps(str(lnk))}); "
        f"$s.TargetPath = {json.dumps(str(target))}; "
        f"$s.WorkingDirectory = {json.dumps(str(workdir))}; "
        f"$s.Description = {json.dumps(description)}; "
        "$s.Save()"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "unbekannt").strip()
        log(f"Verknuepfung fehlgeschlagen ({lnk.name}): {err}\n")
        return
    log(f"Verknuepfung erstellt: {lnk}\n")


def create_control_panel_shortcut(root: Path, log: callable) -> None:
    panel_cmd = (root / "gastro-host" / "run-control-panel.cmd").resolve()
    if not panel_cmd.is_file():
        log("run-control-panel.cmd nicht gefunden – kein Shortcut.\n")
        return
    _create_shortcut(
        desktop_dir() / "Gastro-System.lnk",
        panel_cmd,
        panel_cmd.parent,
        "Gastro-System Control Panel",
        log,
    )


def create_uninstall_shortcut(root: Path, log: callable) -> None:
    un = (root / "gastro-host" / "uninstall.cmd").resolve()
    if not un.is_file():
        log("uninstall.cmd fehlt – keine Deinstallations-Verknuepfung.\n")
        return
    _create_shortcut(
        desktop_dir() / "Gastro deinstallieren.lnk",
        un,
        un.parent,
        "Gastro-System deinstallieren",
        log,
    )


def register_windows_uninstall(root: Path, log: callable) -> None:
    """Eintrag unter Einstellungen > Apps, zeigt Uninstaller."""
    if sys.platform != "win32":
        return
    un_cmd = root / "gastro-host" / "uninstall.cmd"
    display_icon = root / "gastro-host" / "run-control-panel.cmd"
    ps = f"""
$ErrorActionPreference = 'Stop'
$path = 'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\GastroSystem'
New-Item -Path $path -Force | Out-Null
Set-ItemProperty -Path $path -Name 'DisplayName' -Value 'Gastro-System'
Set-ItemProperty -Path $path -Name 'Publisher' -Value 'Gastro-System'
Set-ItemProperty -Path $path -Name 'InstallLocation' -Value {json.dumps(str(root))}
Set-ItemProperty -Path $path -Name 'UninstallString' -Value {json.dumps(str(un_cmd))}
Set-ItemProperty -Path $path -Name 'DisplayVersion' -Value '1.0'
Set-ItemProperty -Path $path -Name 'NoModify' -Value 1 -Type DWord
Set-ItemProperty -Path $path -Name 'NoRepair' -Value 1 -Type DWord
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if r.returncode != 0:
        log(f"Windows-Uninstall-Eintrag fehlgeschlagen: {(r.stderr or r.stdout or '').strip()}\n")
    else:
        log("Windows-Apps-Eintrag (Deinstallieren) registriert.\n")


INCOMPLETE_MARKER = ".gastro-install-incomplete"


def mark_install_incomplete(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / INCOMPLETE_MARKER).write_text("incomplete\n", encoding="ascii")


def clear_install_incomplete(root: Path) -> None:
    p = root / INCOMPLETE_MARKER
    if p.is_file():
        p.unlink(missing_ok=True)


def rollback_failed_install(
    root: Path,
    *,
    created_fresh: bool,
    log: callable,
) -> None:
    """Bei Fehler: unvollstaendige Installation entfernen, kein Muell auf dem PC."""
    log("\n=== FEHLER – Installation wird zurueckgerollt ===\n")
    # Tasks / Shortcuts die wir ggf. schon angelegt haben
    for tn in ("GastroBackend", "GastroFrontend", "GastroCloudflared"):
        subprocess.run(
            ["schtasks", "/Delete", "/TN", tn, "/F"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    for name in ("Gastro-System.lnk", "Gastro deinstallieren.lnk"):
        for base in (desktop_dir(), Path(os.environ.get("PUBLIC", "")) / "Desktop"):
            lnk = base / name
            if lnk.is_file():
                try:
                    lnk.unlink()
                    log(f"Verknuepfung entfernt: {lnk}\n")
                except OSError:
                    pass
    # Registry
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Remove-Item -Path 'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\GastroSystem' -Recurse -Force -ErrorAction SilentlyContinue",
        ],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    marker = root / INCOMPLETE_MARKER
    should_wipe = created_fresh or marker.is_file()
    if should_wipe and root.exists():
        log(f"Entferne unvollstaendigen Ordner: {root}\n")
        # Stop approx. processes in that tree
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-CimInstance Win32_Process -EA SilentlyContinue | "
                f"Where-Object {{ $_.CommandLine -like '*{str(root).replace(chr(92), chr(92)+chr(92))}*' }} | "
                f"ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }}",
            ],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:
            shutil.rmtree(root, ignore_errors=False)
            log("Rollback: Ordner geloescht.\n")
        except OSError as exc:
            log(f"Rollback: Ordner teilweise belegt ({exc}) – restliche Dateien werden bestmoeglich entfernt.\n")
            shutil.rmtree(root, ignore_errors=True)
    else:
        log(
            "Rollback: bestehender Ordner nicht komplett geloescht "
            "(keine Incomplete-Markierung / kein frischer Ordner).\n"
            "Bitte fehlerhafte Reste manuell pruefen oder Uninstaller nutzen.\n"
        )
    log("Installation abgebrochen – kein erfolgreicher Abschluss.\n")


def ensure_venv(
    root: Path,
    log: callable,
    allow_online: bool = False,
    python_exe: Path | None = None,
    force_recreate: bool = True,
) -> Path:
    """venv + Flask offline. python_exe MUSS gepruefte CPython 3.12 sein – nie PATH/Inkscape.
    Gibt den Pfad zu venv\\Scripts\\python.exe zurueck."""
    py_path = python_exe or find_python()
    if py_path and not _is_usable_python(py_path):
        py_path = None
    if not py_path and _is_usable_python(PY_TARGET_EXE):
        py_path = PY_TARGET_EXE
    if not py_path:
        py_path = wait_for_usable_python(log)
    if not py_path:
        raise RuntimeError(
            "Keine nutzbare Python 3.12 gefunden (Inkscape-/Store-Python wird ignoriert)."
        )
    # Nochmals hart gegen Inkscape absichern
    if "inkscape" in str(py_path).lower():
        raise RuntimeError(f"Inkscape-Python verweigert: {py_path}")
    py = str(py_path)
    log(f"venv mit: {py}\n")

    venv = root / "venv"
    venv_py = venv / "Scripts" / "python.exe"
    if force_recreate and venv.exists():
        log("Altes venv wird geloescht und neu aufgebaut …\n")
        shutil.rmtree(venv, ignore_errors=True)
    elif venv.is_dir() and not venv_py.is_file():
        log("Unvollstaendiges venv wird neu erstellt …\n")
        shutil.rmtree(venv, ignore_errors=True)
    if not venv_py.is_file():
        log("Erstelle Python-venv …\n")
        subprocess.run(
            [py, "-m", "venv", str(venv)],
            cwd=str(root),
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    if not venv_py.is_file():
        raise RuntimeError(f"venv-Python fehlt nach Erstellung: {venv_py}")

    req = root / "requirements.txt"
    if not install_python_packages(venv_py, req, log, allow_online=allow_online):
        raise RuntimeError(
            "Python-Abhaengigkeiten (Flask) konnten offline nicht installiert werden. "
            "Wheels fehlen oder passen nicht zu Python 3.12."
        )
    r = subprocess.run(
        [
            str(venv_py),
            "-c",
            "import flask, flask_cors; from flask import Flask; print('ok')",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if r.returncode != 0:
        raise RuntimeError(
            "Flask-Import fehlgeschlagen nach Installation:\n"
            + (r.stderr or r.stdout or "")
        )
    # Backend-Import wie beim echten Start (Arbeitsverzeichnis backend)
    r3 = subprocess.run(
        [
            str(venv_py),
            "-c",
            "import sys; sys.path.insert(0, r'%s'); import main; print('BACKEND_OK')"
            % str(root / "backend").replace("\\", "\\\\"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(root / "backend"),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if r3.returncode != 0:
        raise RuntimeError(
            "Backend-Import fehlgeschlagen (DB/Module):\n"
            + (r3.stderr or r3.stdout or "")
        )
    log("Python-Umgebung bereit (Flask + Backend OK).\n")
    return venv_py.resolve()


def add_hint(parent: tk.Widget, text: str) -> None:
    box = ttk.LabelFrame(parent, text="Anleitung", padding=10)
    box.pack(fill="x", pady=(10, 0))
    ttk.Label(box, text=text, wraplength=680, justify="left").pack(anchor="w")


class SetupWizard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x640")
        self.minsize(680, 520)
        self._step = 0
        self._ip_ok = False
        self._build_vars()
        self._build_ui()
        self._show_step(0)

    def _build_vars(self) -> None:
        self.var_dir = tk.StringVar(value=DEFAULT_INSTALL)
        self.var_ip = tk.StringVar()
        self.var_ip_status = tk.StringVar(value="IP noch nicht geprüft.")
        self.var_cf = tk.BooleanVar(value=False)
        self.var_tunnel = tk.StringVar(value="gastro-system")
        self.var_cred = tk.StringVar()
        self.var_app_host = tk.StringVar()
        self.var_api_host = tk.StringVar()
        cf_path = find_cloudflared()
        self.var_cf_exe = tk.StringVar(value=str(cf_path) if cf_path else DEFAULT_CF_EXE)
        self.var_autostart = tk.BooleanVar(value=True)
        self.var_desktop_shortcut = tk.BooleanVar(value=True)
        self.var_install_python = tk.BooleanVar(value=find_python() is None)
        self.var_install_cloudflared = tk.BooleanVar(value=find_cloudflared() is None)
        self.var_progress = tk.DoubleVar(value=0)
        self.var_status = tk.StringVar(value="Bereit zur Installation.")
        self._install_done = False
        self._install_failed = False

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        head = ttk.Frame(self)
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        ttk.Label(head, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.lbl_step = ttk.Label(head, text="", font=("Segoe UI", 10))
        self.lbl_step.pack(anchor="w", pady=(2, 0))
        self.body = ttk.Frame(self, padding=16)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(0, weight=1)

        self.pages: list[ttk.Frame] = []
        self.pages.append(self._page_welcome())
        self.pages.append(self._page_directory())
        self.pages.append(self._page_network())
        self.pages.append(self._page_cloudflare())
        self.pages.append(self._page_summary())

        nav = ttk.Frame(self)
        nav.grid(row=2, column=0, sticky="ew", padx=16, pady=12)
        nav.columnconfigure(1, weight=1)
        self.btn_back = ttk.Button(nav, text="Zurück", command=self._back)
        self.btn_back.grid(row=0, column=0, padx=(0, 8))
        self.btn_next = ttk.Button(nav, text="Weiter", command=self._next)
        self.btn_next.grid(row=0, column=2, padx=(8, 0))
        self.btn_cancel = ttk.Button(nav, text="Abbrechen", command=self.destroy)
        self.btn_cancel.grid(row=0, column=3, padx=(8, 0))

    def _page_welcome(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        ttk.Label(
            f,
            text="Willkommen",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        add_hint(
            f,
            "Dieses Setup installiert Gastro vollständig – auch ohne Internet.\n"
            "Python 3.12 und Flask liegen im Installer (Offline-Bundle).\n\n"
            "WICHTIG für Offline/Event:\n"
            "• Cloudflare im nächsten Schritt AUS lassen\n"
            "• LAN-IP des PCs wählen (nicht die Fritzbox-Router-IP)\n\n"
            "Danach: Desktop-Link Gastro-System → Gastro-System starten.",
        )
        status = ttk.LabelFrame(f, text="Aktueller Stand auf diesem PC", padding=10)
        status.pack(fill="x", pady=12)
        ttk.Label(status, text=f"Python: {python_version_label()}", wraplength=680).pack(
            anchor="w"
        )
        ttk.Label(
            status, text=f"Offline-Bundle: {offline_ready_label()}", wraplength=680
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            status, text=f"cloudflared: {cloudflared_version_label()}", wraplength=680
        ).pack(anchor="w", pady=(6, 0))
        return f

    def _page_directory(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        ttk.Label(f, text="Installationsordner", font=("Segoe UI", 12, "bold")).pack(
            anchor="w"
        )
        add_hint(
            f,
            "Hier liegt das gesamte Gastro-System inkl. Datenbank (Ordner data).\n\n"
            "• Empfohlen: C:\\Applikationen\\Gastro-System\n"
            "• Der Ordner darf bereits existieren (Update); vorhandene data\\database.db bleibt erhalten.\n"
            "• Wählen Sie ein Laufwerk mit ausreichend freiem Speicher (ca. 500 MB).",
        )
        row = ttk.Frame(f)
        row.pack(fill="x", pady=12)
        ttk.Entry(row, textvariable=self.var_dir, width=70).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Durchsuchen…", command=self._browse_dir).pack(side="left", padx=8)
        return f

    def _page_network(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        ttk.Label(f, text="Netzwerk / LAN-IP", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        add_hint(
            f,
            "Kellner-Tablets und Handys im gleichen WLAN erreichen die Oberfläche unter "
            "http://<LAN-IP>:8081\n\n"
            "1. „IPs aktualisieren“ – zeigt Adressen dieses PCs\n"
            "2. Die passende LAN-IP wählen (meist 192.168.x.x)\n"
            "3. „IP prüfen“ – Pflicht, bevor Sie weitergehen\n\n"
            "Die gewählte IP wird in der Konfiguration gespeichert.",
        )
        row = ttk.Frame(f)
        row.pack(fill="x", pady=8)
        self.ip_combo = ttk.Combobox(row, textvariable=self.var_ip, width=24, state="readonly")
        self.ip_combo.pack(side="left")
        ttk.Button(row, text="IPs aktualisieren", command=self._refresh_ips).pack(
            side="left", padx=8
        )
        ttk.Button(row, text="IP prüfen", command=self._check_ip).pack(side="left")
        ttk.Label(f, textvariable=self.var_ip_status, wraplength=640, foreground="#2ecc71").pack(
            anchor="w", pady=8
        )
        self._refresh_ips()
        return f

    def _page_cloudflare(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        ttk.Label(f, text="Cloudflare Tunnel", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.cf_frame = ttk.Frame(f)
        self.cf_frame.pack(fill="both", expand=True, pady=8)

        add_hint(
            f,
            "Nur aktivieren, wenn Sie Gastro von unterwegs per HTTPS (z. B. app.ihre-domain.de) "
            "nutzen wollen. Dafür brauchen Sie einen Cloudflare-Account und eine Domain bei Cloudflare.\n\n"
            "Ohne Tunnel: Zugriff nur im WLAN über die LAN-IP (vorheriger Schritt).\n"
            "Ausführliche Schritte in Cloudflare: Button „Cloudflare-Anleitung anzeigen“.",
        )

        ttk.Checkbutton(
            f,
            text="Cloudflare Tunnel aktivieren (öffentlicher HTTPS-Zugriff)",
            variable=self.var_cf,
            command=self._toggle_cf,
        ).pack(anchor="w", pady=(8, 0))

        self.cb_install_cf = ttk.Checkbutton(
            f,
            text="cloudflared auf diesem PC installieren (falls noch nicht vorhanden)",
            variable=self.var_install_cloudflared,
        )
        self.cb_install_cf.pack(anchor="w", pady=(4, 0))

        inner = ttk.LabelFrame(self.cf_frame, text="Tunnel-Daten", padding=10)
        inner.pack(fill="x", pady=8)
        self._cf_inner = inner

        def row(label: str, var: tk.StringVar, browse: str | None = None) -> None:
            r = ttk.Frame(inner)
            r.pack(fill="x", pady=4)
            ttk.Label(r, text=label, width=22).pack(side="left")
            ttk.Entry(r, textvariable=var, width=48).pack(side="left", fill="x", expand=True)
            if browse == "file":
                ttk.Button(
                    r, text="…", width=3, command=lambda v=var: self._browse_file(v)
                ).pack(side="left", padx=4)
            elif browse == "exe":
                ttk.Button(
                    r, text="…", width=3, command=lambda v=var: self._browse_exe(v)
                ).pack(side="left", padx=4)

        row("Tunnel-Name:", self.var_tunnel)
        row("Credentials-JSON:", self.var_cred, "file")
        row("Hostname App:", self.var_app_host)
        row("Hostname API:", self.var_api_host)
        row("cloudflared.exe:", self.var_cf_exe, "exe")

        ttk.Button(
            f,
            text="Cloudflare-Anleitung anzeigen",
            command=self._show_cf_guide,
        ).pack(anchor="w", pady=4)
        self._toggle_cf()
        return f

    def _page_summary(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        ttk.Label(f, text="Installation starten", font=("Segoe UI", 12, "bold")).pack(
            anchor="w"
        )
        add_hint(
            f,
            "Mit „Installieren“ starten. Der Fortschrittsbalken und der Status zeigen den Stand.\n"
            "Bei Fehler wird die Installation abgebrochen und unvollständige Dateien entfernt.\n"
            "Kein Internet nötig. Dauer typisch 2–5 Minuten.",
        )
        opts = ttk.LabelFrame(f, text="Optionen", padding=10)
        opts.pack(fill="x", pady=8)
        ttk.Checkbutton(
            opts,
            text="Python 3 installieren, falls noch nicht vorhanden (offline aus Bundle)",
            variable=self.var_install_python,
        ).pack(anchor="w")
        ttk.Checkbutton(
            opts,
            text="Desktop-Verknüpfung „Gastro-System“ zum Control Panel erstellen",
            variable=self.var_desktop_shortcut,
        ).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(
            opts,
            text="Nach jedem PC-Start automatisch Backend + Frontend starten (Windows-Aufgabenplanung)",
            variable=self.var_autostart,
        ).pack(anchor="w", pady=(6, 0))

        prog = ttk.LabelFrame(f, text="Fortschritt", padding=10)
        prog.pack(fill="x", pady=(8, 0))
        self.progress = ttk.Progressbar(
            prog, maximum=100, variable=self.var_progress, mode="determinate"
        )
        self.progress.pack(fill="x")
        self.lbl_status = ttk.Label(
            prog, textvariable=self.var_status, wraplength=680, foreground="#333"
        )
        self.lbl_status.pack(anchor="w", pady=(6, 0))

        self.summary = scrolledtext.ScrolledText(
            f, height=9, wrap="word", font=("Consolas", 10)
        )
        self.summary.pack(fill="both", expand=True, pady=8)
        return f

    def _show_step(self, n: int) -> None:
        for p in self.pages:
            p.pack_forget()
        self.pages[n].pack(fill="both", expand=True)
        self._step = n
        self.lbl_step.configure(
            text=f"Schritt {n + 1} von {len(self.pages)}: {STEP_TITLES[n]}"
        )
        self.btn_back.state = tk.NORMAL if n > 0 else tk.DISABLED
        if n == len(self.pages) - 1:
            if self._install_done:
                self.btn_next.configure(text="Beenden", command=self.destroy)
                self.btn_back.state = tk.DISABLED
            elif self._install_failed:
                self.btn_next.configure(text="Erneut versuchen", command=self._install)
            else:
                self.btn_next.configure(text="Installieren", command=self._install)
            self._fill_summary()
        else:
            self.btn_next.configure(text="Weiter", command=self._next)

    def _back(self) -> None:
        if self._step > 0:
            self._show_step(self._step - 1)

    def _next(self) -> None:
        if self._step == 1:
            d = Path(self.var_dir.get().strip())
            if not d:
                messagebox.showerror(APP_TITLE, "Bitte Installationsordner angeben.")
                return
        if self._step == 2:
            if not self._ip_ok:
                messagebox.showwarning(
                    APP_TITLE, "Bitte zuerst „IP prüfen“ ausführen."
                )
                return
        if self._step == 3 and self.var_cf.get():
            if not self._validate_cf():
                return
        if self._step < len(self.pages) - 1:
            self._show_step(self._step + 1)

    def _browse_dir(self) -> None:
        p = filedialog.askdirectory(initialdir=self.var_dir.get() or "C:\\")
        if p:
            self.var_dir.set(p)

    def _browse_file(self, var: tk.StringVar) -> None:
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("Alle", "*.*")])
        if p:
            var.set(p)

    def _browse_exe(self, var: tk.StringVar) -> None:
        p = filedialog.askopenfilename(filetypes=[("EXE", "*.exe")])
        if p:
            var.set(p)

    def _refresh_ips(self) -> None:
        ips = list_lan_ips()
        self.ip_combo["values"] = ips
        if ips:
            self.var_ip.set(ips[0])
        self.var_ip_status.set("IP-Liste aktualisiert – bitte „IP prüfen“.")

    def _check_ip(self) -> None:
        ok, msg = verify_ip(self.var_ip.get())
        self._ip_ok = ok
        self.var_ip_status.set(msg)
        self.summary_tag_color = "#2ecc71" if ok else "#e74c3c"

    def _toggle_cf(self) -> None:
        on = self.var_cf.get()
        state = tk.NORMAL if on else tk.DISABLED
        self.cb_install_cf.configure(state=state)
        for child in self._cf_inner.winfo_children():
            try:
                for w in child.winfo_children():
                    w.configure(state=state)
            except tk.TclError:
                pass

    def _validate_cf(self) -> bool:
        if not Path(self.var_cred.get().strip()).is_file():
            messagebox.showerror(APP_TITLE, "Credentials-JSON auswählen.")
            return False
        if not self.var_app_host.get().strip() or not self.var_api_host.get().strip():
            messagebox.showerror(APP_TITLE, "App- und API-Hostname angeben.")
            return False
        exe = Path(self.var_cf_exe.get().strip())
        if not exe.is_file() and not self.var_install_cloudflared.get():
            messagebox.showerror(
                APP_TITLE,
                "cloudflared.exe nicht gefunden.\n"
                "Haken „cloudflared installieren“ setzen oder Pfad wählen.",
            )
            return False
        return True

    def _show_cf_guide(self) -> None:
        gp = guide_path()
        if gp.is_file():
            webbrowser.open(gp.as_uri())
        else:
            messagebox.showinfo(APP_TITLE, f"Anleitung nicht gefunden:\n{gp}")

    def _fill_summary(self) -> None:
        self.summary.delete("1.0", tk.END)
        lines = [
            f"Installationsordner: {self.var_dir.get().strip()}",
            f"LAN-IP: {self.var_ip.get()} ({'geprüft' if self._ip_ok else 'nicht geprüft'})",
            f"Cloudflare: {'Ja' if self.var_cf.get() else 'Nein'}",
            f"Desktop-Verknüpfung: {'Ja' if self.var_desktop_shortcut.get() else 'Nein'}",
            f"Python installieren: {'Ja' if self.var_install_python.get() else 'Nein'}",
            f"Windows-Aufgaben (Autostart): {'Ja' if self.var_autostart.get() else 'Nein'}",
        ]
        if self.var_cf.get():
            lines += [
                f"  Tunnel: {self.var_tunnel.get()}",
                f"  App: {self.var_app_host.get()}",
                f"  API: {self.var_api_host.get()}",
            ]
        self.summary.insert(tk.END, "\n".join(lines))

    def _set_progress(self, pct: float, status: str, *, error: bool = False) -> None:
        def _ui() -> None:
            self.var_progress.set(max(0, min(100, abs(pct) if error else pct)))
            self.var_status.set(status)
            try:
                if error:
                    color = "#8b3a3a"
                elif pct >= 100:
                    color = "#1a6b3a"
                else:
                    color = "#333"
                self.lbl_status.configure(foreground=color)
            except tk.TclError:
                pass

        self.after(0, _ui)

    def _install(self) -> None:
        if self._install_done:
            self.destroy()
            return
        root = Path(self.var_dir.get().strip())
        lan_ip = self.var_ip.get().strip()
        cf = self.var_cf.get()
        created_fresh = not root.exists()
        self._install_failed = False
        self._install_done = False

        def log(msg: str) -> None:
            def _ui() -> None:
                self.summary.insert(tk.END, msg)
                self.summary.see(tk.END)

            self.after(0, _ui)

        self.btn_next.configure(text="Installiere …", state=tk.DISABLED)
        self.btn_back.state = tk.DISABLED
        self.btn_cancel.state = tk.DISABLED
        self._set_progress(1, "Installation gestartet …")
        self.summary.insert(tk.END, "\n\n===== Installation =====\n")

        def work() -> None:
            ok = False
            handbook_path: Path | None = None
            panel_cmd = root / "gastro-host" / "run-control-panel.cmd"
            try:
                allow_online = False
                self._set_progress(5, "Pruefe Offline-Bundle …")
                log("=== Offline-Bundle ===\n")
                require_offline_bundle(log)

                self._set_progress(12, "Python 3.12 …")
                log("=== Python ===\n")
                if not install_python(log, allow_online=allow_online):
                    raise RuntimeError(
                        "Python 3.12 konnte nicht offline installiert werden.\n"
                        "Als Administrator ausfuehren. Inkscape-Python wird nicht verwendet."
                    )
                py_ok = wait_for_usable_python(log)
                if not py_ok:
                    raise RuntimeError(
                        "Keine nutzbare Python 3.12 nach Installation.\n"
                        "PC neu starten und Setup erneut als Admin ausfuehren."
                    )
                log(f"Verwende Python: {py_ok}\n")

                if cf and self.var_install_cloudflared.get():
                    self._set_progress(18, "cloudflared …")
                    log("=== cloudflared ===\n")
                    if not install_cloudflared(log, allow_online=allow_online):
                        raise RuntimeError(
                            "cloudflared fehlt im Offline-Bundle. "
                            "Fuer Offline Cloudflare deaktivieren."
                        )
                    found_cf = find_cloudflared()
                    if found_cf:
                        self.var_cf_exe.set(str(found_cf))

                src = repo_root()
                if not (src / "backend" / "main.py").is_file():
                    raise RuntimeError(f"Payload unvollstaendig – backend/main.py fehlt in {src}")
                if not (src / "requirements.txt").is_file():
                    raise RuntimeError(f"Payload unvollstaendig – requirements.txt fehlt in {src}")
                if not (src / "gastro-host" / "uninstall.cmd").is_file():
                    raise RuntimeError("Payload unvollstaendig – uninstall.cmd fehlt")

                self._set_progress(25, "Kopiere Programmdaten …")
                log(f"Quelle: {src}\n")
                mark_install_incomplete(root)
                copy_tree(src, root, log)
                (root / "data").mkdir(parents=True, exist_ok=True)

                if cf:
                    self._set_progress(35, "Cloudflare-Konfiguration …")
                    cred_src = Path(self.var_cred.get().strip())
                    if not cred_src.is_file():
                        raise RuntimeError(
                            "Cloudflare aktiv, aber Credentials-JSON fehlt."
                        )
                    tunnel_id = read_tunnel_id(cred_src)
                    cf_dir = Path.home() / ".cloudflared"
                    cf_dir.mkdir(parents=True, exist_ok=True)
                    cred_dest = cf_dir / f"{tunnel_id}.json"
                    shutil.copy2(cred_src, cred_dest)
                    write_cloudflared_config(
                        root,
                        self.var_tunnel.get().strip() or tunnel_id,
                        cred_dest,
                        self.var_app_host.get(),
                        self.var_api_host.get(),
                    )
                    log(f"Cloudflare config.yml und {cred_dest}\n")

                panel_cmd = root / "gastro-host" / "run-control-panel.cmd"
                host_cfg = {
                    "install_dir": str(root),
                    "lan_ip": lan_ip,
                    "backend_port": 8000,
                    "frontend_port": 8081,
                    "cloudflare": {
                        "enabled": cf,
                        "tunnel_name": self.var_tunnel.get().strip(),
                        "app_hostname": self.var_app_host.get().strip(),
                        "api_hostname": self.var_api_host.get().strip(),
                    },
                    "autostart": self.var_autostart.get(),
                    "desktop_shortcut": self.var_desktop_shortcut.get(),
                    "control_panel_cmd": str(panel_cmd),
                }
                write_host_json(root, host_cfg)

                self._set_progress(50, "Erstelle Python-venv + Flask …")
                log("=== Python-venv (Flask) ===\n")
                venv_py = ensure_venv(
                    root, log, allow_online=False, python_exe=py_ok, force_recreate=True
                )
                write_config_cmd(root, lan_ip, cf, self.var_cf_exe.get().strip())
                log(f"config.cmd geschrieben (GASTRO_PYTHON={venv_py})\n")
                if not venv_py.is_file():
                    raise RuntimeError(f"venv Python fehlt nach Setup: {venv_py}")

                # DB am Installationsort anlegen/verknüpfen (kein hardcodierter Dev-Pfad)
                db_file = (root / "data" / "database.db").resolve()
                log(f"=== Datenbank: {db_file} ===\n")
                init_env = os.environ.copy()
                init_env["GASTRO_DB_PATH"] = str(db_file)
                init_env["GASTRO_ROOT"] = str(root.resolve())
                init = subprocess.run(
                    [
                        str(venv_py),
                        "-c",
                        "from db import get_db_connection; c=get_db_connection(); c.execute('SELECT 1'); c.close(); print('db_ok')",
                    ],
                    cwd=str(root / "backend"),
                    env=init_env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32"
                    else 0,
                )
                if init.returncode != 0 or "db_ok" not in (init.stdout or ""):
                    raise RuntimeError(
                        "Datenbank konnte nicht initialisiert werden: "
                        + ((init.stderr or init.stdout or "").strip() or f"exit {init.returncode}")
                    )
                log("Datenbank initialisiert / bereit.\n")

                self._set_progress(75, "Firewall / LAN …")
                prep = root / "gastro-host" / "prepare-lan.ps1"
                if prep.is_file():
                    log("=== LAN / Firewall ===\n")
                    subprocess.run(
                        [
                            "powershell",
                            "-NoProfile",
                            "-ExecutionPolicy",
                            "Bypass",
                            "-File",
                            str(prep),
                            "-LanIp",
                            lan_ip,
                            *(["-DisableCloudflare"] if not cf else []),
                        ],
                        check=False,
                        creationflags=subprocess.CREATE_NO_WINDOW
                        if sys.platform == "win32"
                        else 0,
                    )
                    log("prepare-lan ausgefuehrt.\n")

                self._set_progress(85, "Verknuepfungen & Autostart …")
                if self.var_desktop_shortcut.get():
                    create_control_panel_shortcut(root, log)
                create_uninstall_shortcut(root, log)
                register_windows_uninstall(root, log)

                if self.var_autostart.get():
                    ps1 = root / "gastro-host" / "register-gastro-tasks.ps1"
                    if ps1.is_file():
                        ps_args = [
                            "powershell",
                            "-NoProfile",
                            "-ExecutionPolicy",
                            "Bypass",
                            "-File",
                            str(ps1),
                            "-InstallRoot",
                            str(root),
                        ]
                        if cf:
                            ps_args.append("-CloudflareEnabled")
                        r_task = subprocess.run(ps_args, capture_output=True, text=True)
                        if r_task.returncode != 0:
                            raise RuntimeError(
                                "Autostart-Aufgaben fehlgeschlagen:\n"
                                + (r_task.stderr or r_task.stdout or "")
                            )
                        log(
                            "Windows-Aufgaben registriert "
                            "(GastroBackend, GastroFrontend"
                            + (", GastroCloudflared" if cf else "")
                            + ").\n"
                        )

                handbook_path = write_install_handbook(root, host_cfg)
                log(f"Nutzungsanleitung: {handbook_path}\n")

                # Erfolg erst jetzt – Marker entfernen
                clear_install_incomplete(root)
                ok = True
                self._set_progress(100, "Installation erfolgreich abgeschlossen.")
                log("\n=== FERTIG – Installation erfolgreich ===\n")

                def _finish_ok() -> None:
                    self._install_done = True
                    self._install_failed = False
                    self.btn_next.configure(text="Beenden", state=tk.NORMAL, command=self.destroy)
                    self.btn_back.state = tk.DISABLED
                    self.btn_cancel.state = tk.DISABLED
                    try:
                        if handbook_path:
                            webbrowser.open(handbook_path.as_uri())
                    except OSError:
                        pass
                    messagebox.showinfo(
                        APP_TITLE,
                        "Installation erfolgreich abgeschlossen.\n\n"
                        f"Control Panel: {panel_cmd}\n"
                        f"LAN: http://{lan_ip}:8081\n\n"
                        "Deinstallieren: Desktop „Gastro deinstallieren“\n"
                        "oder Windows-Einstellungen → Apps.",
                    )

                self.after(0, _finish_ok)
            except Exception as exc:
                try:
                    rollback_failed_install(
                        root, created_fresh=created_fresh, log=log
                    )
                except Exception as rb_exc:
                    log(f"Rollback-Zusatzfehler: {rb_exc}\n")
                self._set_progress(
                    0, "Installation fehlgeschlagen – zurueckgerollt.", error=True
                )

                def _finish_err(e: Exception = exc) -> None:
                    self._install_done = False
                    self._install_failed = True
                    self.btn_next.configure(
                        text="Erneut versuchen", state=tk.NORMAL, command=self._install
                    )
                    self.btn_back.state = tk.NORMAL
                    self.btn_cancel.state = tk.NORMAL
                    messagebox.showerror(
                        APP_TITLE,
                        "Installation fehlgeschlagen.\n\n"
                        f"{e}\n\n"
                        "Unvollstaendige Dateien wurden entfernt.\n"
                        "Bitte Fehler beheben und „Erneut versuchen“.",
                    )

                self.after(0, _finish_err)
            finally:
                if not ok:

                    def _unlock_fail() -> None:
                        # Buttons werden in _finish_err gesetzt; Sicherheit
                        if self._install_failed:
                            self.btn_next.configure(state=tk.NORMAL)
                            self.btn_back.configure(state=tk.NORMAL)
                            self.btn_cancel.configure(state=tk.NORMAL)

                    self.after(0, _unlock_fail)

        threading.Thread(target=work, daemon=True).start()


def main() -> None:
    request_admin_at_startup()
    SetupWizard().mainloop()


if __name__ == "__main__":
    main()
