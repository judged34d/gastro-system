"""Windows-Voraussetzungen: Admin, Python, cloudflared."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_TITLE = "Gastro-System Setup"
DEFAULT_CF_EXE = Path(r"C:\Program Files\cloudflared\cloudflared.exe")
PYTHON_WINGET_ID = "Python.Python.3.12"
CF_WINGET_ID = "Cloudflare.cloudflared"
PY_INSTALL_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"


def _win_no_window() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def request_admin_at_startup() -> None:
    """UAC-Abfrage beim Start; beendet diese Instanz nach Relaunch als Admin."""
    if sys.platform != "win32" or is_admin():
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            "Das Setup benötigt Administratorrechte, um:\n"
            "• Python und (optional) cloudflared zu installieren\n"
            "• Windows-Aufgaben für den Autostart anzulegen\n"
            "• Dateien im gewählten Programmordner zu schreiben\n\n"
            "Bitte im nächsten Dialog auf „Ja“ klicken.",
            APP_TITLE,
            0x40,
        )
        if getattr(sys, "frozen", False):
            executable = sys.executable
            params = subprocess.list2cmdline(sys.argv[1:])
        else:
            executable = sys.executable
            params = subprocess.list2cmdline([str(Path(sys.argv[0]).resolve()), *sys.argv[1:]])
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params or "", None, 1
        )
        if rc <= 32:
            ctypes.windll.user32.MessageBoxW(
                0,
                "Administratorrechte wurden abgelehnt.\n"
                "Das Setup kann nicht fortgesetzt werden.",
                APP_TITLE,
                0x10,
            )
    except OSError:
        pass
    sys.exit(0)


def winget_available() -> bool:
    return shutil.which("winget") is not None


def _run_logged(cmd: list[str], log: callable, timeout: int = 600) -> bool:
    log(f"> {' '.join(cmd)}\n")
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_win_no_window(),
    )
    if r.stdout:
        log(r.stdout.strip() + "\n")
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "Fehler").strip()
        log(f"FEHLER: {err}\n")
        return False
    return True


def find_python() -> Path | None:
    for name in ("python", "python3"):
        p = shutil.which(name)
        if p:
            return Path(p)
    try:
        r = subprocess.run(
            ["py", "-3", "-c", "import sys; print(sys.executable)"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_win_no_window(),
        )
        if r.returncode == 0:
            line = (r.stdout or "").strip().splitlines()[-1]
            if line and Path(line).is_file():
                return Path(line)
    except (OSError, subprocess.SubprocessError):
        pass
    for pattern in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python",
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
    ):
        if not pattern.is_dir():
            continue
        for exe in pattern.rglob("python.exe"):
            if "WindowsApps" in str(exe):
                continue
            return exe
    return None


def install_python(log: callable) -> bool:
    if find_python():
        log(f"Python bereits vorhanden: {find_python()}\n")
        return True
    if winget_available():
        log("Installiere Python 3.12 über winget …\n")
        ok = _run_logged(
            [
                "winget",
                "install",
                "-e",
                "--id",
                PYTHON_WINGET_ID,
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            log,
            timeout=900,
        )
        if ok and find_python():
            return True
        log("winget-Installation nicht verifiziert – versuche Download …\n")
    return _install_python_download(log)


def _install_python_download(log: callable) -> bool:
    import urllib.request

    dest = Path(os.environ.get("TEMP", ".")) / "python-gastro-setup.exe"
    log(f"Lade Python-Installer …\n{PY_INSTALL_URL}\n")
    try:
        urllib.request.urlretrieve(PY_INSTALL_URL, dest)
    except OSError as exc:
        log(f"Download fehlgeschlagen: {exc}\n")
        return False
    log("Starte stille Python-Installation (ca. 2–3 Min.) …\n")
    args = [
        str(dest),
        "/quiet",
        "InstallAllUsers=1",
        "PrependPath=1",
        "Include_test=0",
        "Include_launcher=1",
    ]
    r = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        log(f"Python-Setup fehlgeschlagen: {(r.stderr or '').strip()}\n")
        return False
    found = find_python()
    if found:
        log(f"Python installiert: {found}\n")
        return True
    log("Python-Installer beendet, aber python.exe nicht gefunden. PC ggf. neu starten.\n")
    return False


def find_cloudflared() -> Path | None:
    if DEFAULT_CF_EXE.is_file():
        return DEFAULT_CF_EXE
    p = shutil.which("cloudflared")
    return Path(p) if p else None


def install_cloudflared(log: callable) -> bool:
    found = find_cloudflared()
    if found:
        log(f"cloudflared bereits vorhanden: {found}\n")
        return True
    if winget_available():
        log("Installiere cloudflared über winget …\n")
        if _run_logged(
            [
                "winget",
                "install",
                "-e",
                "--id",
                CF_WINGET_ID,
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            log,
            timeout=600,
        ):
            found = find_cloudflared()
            if found:
                return True
    return _install_cloudflared_download(log)


def _install_cloudflared_download(log: callable) -> bool:
    import urllib.request

    dest_dir = Path(r"C:\Program Files\cloudflared")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "cloudflared.exe"
    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    log(f"Lade cloudflared …\n{url}\n")
    try:
        urllib.request.urlretrieve(url, dest)
    except OSError as exc:
        log(f"Download fehlgeschlagen: {exc}\n")
        return False
    if dest.is_file():
        log(f"cloudflared installiert: {dest}\n")
        return True
    return False


def python_version_label() -> str:
    p = find_python()
    if not p:
        return "nicht gefunden (wird bei Installation nachinstalliert)"
    try:
        r = subprocess.run(
            [str(p), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_win_no_window(),
        )
        ver = (r.stdout or r.stderr or "").strip()
        return f"{ver} – {p}"
    except (OSError, subprocess.SubprocessError):
        return str(p)


def cloudflared_version_label() -> str:
    p = find_cloudflared()
    if not p:
        return "nicht gefunden"
    try:
        r = subprocess.run(
            [str(p), "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_win_no_window(),
        )
        line = (r.stdout or r.stderr or "").strip().splitlines()[0]
        return f"{line} – {p}"
    except (OSError, subprocess.SubprocessError):
        return str(p)
