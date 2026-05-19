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
    cloudflared_version_label,
    find_cloudflared,
    find_python,
    install_cloudflared,
    install_python,
    python_version_label,
    request_admin_at_startup,
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
    if src.resolve() == dst.resolve():
        log("Quelle = Ziel – Dateien werden nur konfiguriert.\n")
        return
    if dst.exists():
        if not messagebox.askyesno(
            APP_TITLE,
            f"Zielordner existiert bereits:\n{dst}\n\nInhalt aktualisieren/ergänzen?",
        ):
            raise RuntimeError("Installation abgebrochen.")
    for root, dirs, files in os.walk(src):
        rel_root = Path(root).relative_to(src)
        if any(should_skip_copy(rel_root / d) for d in list(dirs)):
            dirs[:] = [d for d in dirs if not should_skip_copy(rel_root / d)]
        else:
            dirs[:] = [d for d in dirs if d not in SKIP_COPY_NAMES]
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
    lines = [
        "@echo off",
        f'set "GASTRO_ROOT={root}"',
        'set "GASTRO_DB_PATH=%GASTRO_ROOT%\\data\\database.db"',
        "set \"GASTRO_BACKEND_PORT=8000\"",
        "set \"GASTRO_FRONTEND_PORT=8081\"",
        'set "GASTRO_PYTHON=%GASTRO_ROOT%\\venv\\Scripts\\python.exe"',
        f'set "GASTRO_LAN_IP={lan_ip}"',
        f'set "GASTRO_CLOUDFLARED_ENABLED={"1" if cf_enabled else "0"}"',
        f'set "GASTRO_CLOUDFLARED_EXE={cf_exe}"',
        'set "GASTRO_CLOUDFLARED_CFG=%GASTRO_ROOT%\\cloudflared\\config.yml"',
        "",
    ]
    host.write_text("\n".join(lines), encoding="utf-8", newline="\r\n")


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


def create_control_panel_shortcut(root: Path, log: callable) -> None:
    """Verknüpfung auf dem Desktop zum Control Panel (nur Windows)."""
    if sys.platform != "win32":
        log("Desktop-Verknüpfung: nur unter Windows verfügbar.\n")
        return
    panel_cmd = (root / "gastro-host" / "run-control-panel.cmd").resolve()
    if not panel_cmd.is_file():
        log("run-control-panel.cmd nicht gefunden – kein Shortcut.\n")
        return
    desktop = desktop_dir()
    desktop.mkdir(parents=True, exist_ok=True)
    lnk = desktop / "Gastro-System.lnk"
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut({json.dumps(str(lnk))}); "
        f"$s.TargetPath = {json.dumps(str(panel_cmd))}; "
        f"$s.WorkingDirectory = {json.dumps(str(panel_cmd.parent))}; "
        "$s.Description = 'Gastro-System Control Panel'; "
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
        log(f"Desktop-Verknüpfung fehlgeschlagen: {err}\n")
        return
    log(f"Desktop-Verknüpfung erstellt: {lnk}\n")


def ensure_venv(root: Path, log: callable) -> None:
    found = find_python()
    py = str(found) if found else shutil.which("python") or shutil.which("py")
    if not py:
        log("Hinweis: Python nicht im PATH – venv bitte manuell anlegen.\n")
        return
    venv = root / "venv"
    if not venv.is_dir():
        log("Erstelle Python-venv …\n")
        subprocess.run(
            [py, "-m", "venv", str(venv)],
            cwd=str(root),
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    pip = venv / "Scripts" / "pip.exe"
    req = root / "requirements.txt"
    if req.is_file() and pip.is_file():
        log("Installiere Abhängigkeiten …\n")
        subprocess.run(
            [str(pip), "install", "-r", str(req)],
            cwd=str(root),
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )


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
            "Sie haben Administratorrechte bestätigt – das ist nötig, damit das Setup "
            "Python und optional cloudflared installieren sowie Windows-Aufgaben anlegen kann.\n\n"
            "In den nächsten Schritten wählen Sie den Installationsordner, die LAN-Adresse "
            "dieses PCs (für Tablets im WLAN) und optional den Cloudflare-Tunnel fürs Internet.\n\n"
            "Am Ende werden Programmdateien kopiert, Python-Umgebung eingerichtet und Sie können "
            "eine Desktop-Verknüpfung zum Control Panel erhalten.",
        )
        status = ttk.LabelFrame(f, text="Aktueller Stand auf diesem PC", padding=10)
        status.pack(fill="x", pady=12)
        ttk.Label(status, text=f"Python: {python_version_label()}", wraplength=680).pack(
            anchor="w"
        )
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
            "Prüfen Sie die Zusammenfassung im Protokoll unten. Mit „Installieren“ werden "
            "Dateien kopiert, Python-Umgebung (venv) angelegt und die Konfiguration geschrieben.\n\n"
            "Dauer je nach Internet: etwa 5–15 Minuten (Python/cloudflared-Download).",
        )
        opts = ttk.LabelFrame(f, text="Optionen", padding=10)
        opts.pack(fill="x", pady=8)
        ttk.Checkbutton(
            opts,
            text="Python 3 installieren, falls auf diesem PC noch nicht vorhanden",
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
        ttk.Label(
            opts,
            text=(
                "Was bedeutet „Windows-Aufgaben“? Es werden Einträge wie GastroBackend und "
                "GastroFrontend angelegt. Windows führt beim Anmelden die Start-Skripte aus – "
                "Sie müssen die Dienste nach einem Neustart nicht manuell starten. "
                "Bei aktivem Tunnel kommt ggf. GastroCloudflared hinzu."
            ),
            wraplength=680,
            justify="left",
            foreground="#555",
        ).pack(anchor="w", pady=(4, 0), padx=(22, 0))
        self.summary = scrolledtext.ScrolledText(f, height=10, wrap="word", font=("Consolas", 10))
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

    def _install(self) -> None:
        root = Path(self.var_dir.get().strip())
        lan_ip = self.var_ip.get().strip()
        cf = self.var_cf.get()
        log_lines: list[str] = []

        def log(msg: str) -> None:
            log_lines.append(msg)
            self.summary.insert(tk.END, msg)
            self.summary.see(tk.END)
            self.update_idletasks()

        self.btn_next.state = tk.DISABLED
        self.btn_back.state = tk.DISABLED

        def work() -> None:
            try:
                if self.var_install_python.get():
                    log("=== Python ===\n")
                    if not install_python(log):
                        raise RuntimeError(
                            "Python konnte nicht installiert werden. "
                            "Bitte manuell von python.org installieren."
                        )
                if cf and self.var_install_cloudflared.get():
                    log("=== cloudflared ===\n")
                    if not install_cloudflared(log):
                        raise RuntimeError("cloudflared konnte nicht installiert werden.")
                    found_cf = find_cloudflared()
                    if found_cf:
                        self.var_cf_exe.set(str(found_cf))

                src = repo_root()
                log(f"Quelle: {src}\n")
                copy_tree(src, root, log)
                (root / "data").mkdir(parents=True, exist_ok=True)

                cred_dest: Path | None = None
                if cf:
                    cred_src = Path(self.var_cred.get().strip())
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

                write_config_cmd(root, lan_ip, cf, self.var_cf_exe.get().strip())
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
                log("config.cmd und host-config.json geschrieben.\n")
                ensure_venv(root, log)

                if self.var_desktop_shortcut.get():
                    create_control_panel_shortcut(root, log)

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
                        subprocess.run(ps_args, check=False)
                        log(
                            "Windows-Aufgaben für Autostart registriert "
                            "(GastroBackend, GastroFrontend"
                            + (", GastroCloudflared" if cf else "")
                            + ").\n"
                        )

                handbook = write_install_handbook(root, host_cfg)
                log(f"Nutzungsanleitung erstellt:\n{handbook}\n")

                handbook_path = handbook

                def _finish() -> None:
                    try:
                        webbrowser.open(handbook_path.as_uri())
                    except OSError:
                        pass
                    messagebox.showinfo(
                        APP_TITLE,
                        "Installation abgeschlossen.\n\n"
                        f"Nutzungsanleitung (URLs & Bedienung):\n{handbook_path}\n\n"
                        "Das Dokument wurde im Browser geöffnet.\n"
                        f"Control Panel: {panel_cmd}\n"
                        f"LAN: http://{lan_ip}:8081",
                    )

                self.after(0, _finish)
            except Exception as exc:
                self.after(
                    0,
                    lambda e=exc: messagebox.showerror(APP_TITLE, f"Fehler:\n{e}"),
                )
            finally:
                def _unlock() -> None:
                    self.btn_next.configure(state=tk.NORMAL)
                    self.btn_back.configure(state=tk.NORMAL)

                self.after(0, _unlock)

        threading.Thread(target=work, daemon=True).start()


def main() -> None:
    request_admin_at_startup()
    SetupWizard().mainloop()


if __name__ == "__main__":
    main()
