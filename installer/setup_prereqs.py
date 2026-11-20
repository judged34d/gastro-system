"""Windows-Voraussetzungen: Admin, Python, cloudflared – Offline-Bundle first."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

APP_TITLE = "Gastro-System Setup"
DEFAULT_CF_EXE = Path(r"C:\Program Files\cloudflared\cloudflared.exe")
PYTHON_WINGET_ID = "Python.Python.3.12"
CF_WINGET_ID = "Cloudflare.cloudflared"
PY_INSTALL_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
PY_OFFLINE_NAME = "python-3.12.10-amd64.exe"
# Fester Zielordner – muss zu den cp312-Wheels passen
PY_TARGET_DIR = Path(r"C:\Program Files\Python312")
PY_TARGET_EXE = PY_TARGET_DIR / "python.exe"

# Eingebettete/fremde Pythons taugen nicht fuer Gastro-venv.
_BAD_PYTHON_MARKERS = (
    "windowsapps",
    "inkscape",
    "gimp",
    "blender",
    "arcgis",
    "anaconda3\\pkgs",
    "miniconda3\\pkgs",
    "msys64",
    "cygwin",
)


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
            "Das Setup benoetigt Administratorrechte, um:\n"
            "• Python offline zu installieren\n"
            "• Windows-Aufgaben fuer den Autostart anzulegen\n"
            "• Firewall-Regeln und Dateien im Programmordner zu schreiben\n\n"
            "Bitte im naechsten Dialog auf Ja klicken.",
            APP_TITLE,
            0x40,
        )
        if getattr(sys, "frozen", False):
            executable = sys.executable
            params = subprocess.list2cmdline(sys.argv[1:])
        else:
            executable = sys.executable
            params = subprocess.list2cmdline(
                [str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]
            )
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


def app_bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def offline_bundle_dir() -> Path | None:
    """Ordner mit Python-Installer + wheels (+ optional cloudflared)."""
    candidates = [
        app_bundle_dir() / "offline",
        app_bundle_dir() / "payload" / "offline",
        Path(__file__).resolve().parent / "offline",
    ]
    for p in candidates:
        if p.is_dir() and (
            (p / PY_OFFLINE_NAME).is_file() or (p / "wheels").is_dir()
        ):
            return p
    return None


def require_offline_bundle(log: callable | None = None) -> Path:
    """Wirft, wenn das Offline-Bundle unvollstaendig ist."""
    root = offline_bundle_dir()
    py = bundled_python_installer()
    wheels = bundled_wheels_dir()
    msg_parts = []
    if not root:
        msg_parts.append("offline/-Ordner fehlt im Setup")
    if not py:
        msg_parts.append(f"{PY_OFFLINE_NAME} fehlt")
    if not wheels:
        msg_parts.append("wheels/ fehlt oder leer")
    if msg_parts:
        msg = (
            "Offline-Bundle unvollstaendig: "
            + ", ".join(msg_parts)
            + ".\nSetup.exe muss mit fetch-offline-deps.ps1 neu gebaut werden."
        )
        if log:
            log("FEHLER: " + msg + "\n")
        raise RuntimeError(msg)
    assert root is not None
    if log:
        n = len(list(wheels.glob("*.whl")))  # type: ignore[union-attr]
        log(f"Offline-Bundle OK ({root}) – Python-Installer + {n} Wheels\n")
    return root


def bundled_python_installer() -> Path | None:
    root = offline_bundle_dir()
    if not root:
        return None
    p = root / PY_OFFLINE_NAME
    return p if p.is_file() and p.stat().st_size > 1_000_000 else None


def bundled_wheels_dir() -> Path | None:
    root = offline_bundle_dir()
    if not root:
        return None
    w = root / "wheels"
    if w.is_dir() and any(w.glob("*.whl")):
        return w
    return None


def bundled_cloudflared() -> Path | None:
    root = offline_bundle_dir()
    if not root:
        return None
    p = root / "cloudflared.exe"
    return p if p.is_file() and p.stat().st_size > 100_000 else None


def _is_usable_python(path: Path | None) -> bool:
    if not path or not path.is_file():
        return False
    low = str(path).lower().replace("/", "\\")
    if any(m in low for m in _BAD_PYTHON_MARKERS):
        return False
    try:
        r = subprocess.run(
            [
                str(path),
                "-c",
                "import sys; "
                "assert sys.version_info[:2] == (3, 12); "
                "import venv; import ensurepip; "
                "print('%d.%d' % sys.version_info[:2])",
            ],
            capture_output=True,
            text=True,
            timeout=25,
            creationflags=_win_no_window(),
        )
        if r.returncode != 0:
            return False
        ver = (r.stdout or "").strip().splitlines()[-1] if r.stdout else ""
        # Wheels sind cp312 – bevorzugt 3.12, erlaube 3.10/3.11 nur ohne MarkupSafe-Binary-Zwang
        # Wir verlangen 3.12, weil offline/wheels MarkupSafe nur als cp312 enthält.
        return ver.startswith("3.12")
    except (OSError, subprocess.SubprocessError):
        return False


def find_python() -> Path | None:
    """Echte CPython 3.12 finden – nie Inkscape/Store-Stubs."""
    candidates: list[Path] = []

    # 1) Unser fester Installationspfad zuerst
    if PY_TARGET_EXE.is_file():
        candidates.append(PY_TARGET_EXE)

    for fixed in (
        Path(r"C:\Program Files\Python312\python.exe"),
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Python"
        / "Python312"
        / "python.exe",
    ):
        if fixed.is_file():
            candidates.append(fixed)

    try:
        r = subprocess.run(
            ["py", "-3.12", "-c", "import sys; print(sys.executable)"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_win_no_window(),
        )
        if r.returncode == 0:
            line = (r.stdout or "").strip().splitlines()[-1]
            if line:
                candidates.append(Path(line))
    except (OSError, subprocess.SubprocessError):
        pass

    for name in ("python", "python3"):
        p = shutil.which(name)
        if p:
            candidates.append(Path(p))

    # Nur Ordner die mit "python" beginnen – nie ganz Program Files rglob
    for root in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
        Path(r"C:\Program Files"),
    ):
        if not root.is_dir():
            continue
        try:
            for child in root.iterdir():
                if not child.name.lower().startswith("python"):
                    continue
                exe = child / "python.exe"
                if exe.is_file():
                    candidates.append(exe)
        except OSError:
            pass

    seen: set[str] = set()
    for cand in candidates:
        try:
            key = str(cand.resolve())
        except OSError:
            key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if _is_usable_python(cand):
            return cand
    return None


def wait_for_usable_python(log: callable, attempts: int = 15, delay_s: float = 1.0) -> Path | None:
    """Nach stiller Installation: kurz warten bis python.exe nutzbar ist."""
    for i in range(attempts):
        found = find_python()
        if found:
            return found
        if PY_TARGET_EXE.is_file() and _is_usable_python(PY_TARGET_EXE):
            return PY_TARGET_EXE
        log(f"Warte auf Python … ({i + 1}/{attempts})\n")
        time.sleep(delay_s)
    return find_python()


def _install_python_from_file(installer: Path, log: callable) -> bool:
    log(f"Installiere Python 3.12 offline aus Bundle …\n{installer}\n")
    log(f"Zielordner: {PY_TARGET_DIR}\n")
    PY_TARGET_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        str(installer),
        "/quiet",
        "InstallAllUsers=1",
        "PrependPath=1",
        "Include_test=0",
        "Include_launcher=1",
        "Include_tcltk=1",
        "Include_pip=1",
        "Include_doc=0",
        f"TargetDir={PY_TARGET_DIR}",
    ]
    r = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        log(
            f"Python-Setup fehlgeschlagen (Code {r.returncode}): "
            f"{(r.stderr or r.stdout or '').strip()}\n"
        )
        return False
    found = wait_for_usable_python(log)
    if found:
        log(f"Python installiert und geprueft: {found}\n")
        return True
    log(
        "Python-Installer beendet, aber keine nutzbare Python 3.12 gefunden.\n"
        f"Erwartet unter: {PY_TARGET_EXE}\n"
    )
    return False


def install_python(log: callable, allow_online: bool = False) -> bool:
    existing = find_python()
    if existing:
        log(f"Python 3.12 bereits vorhanden: {existing}\n")
        return True

    bundled = bundled_python_installer()
    if bundled:
        return _install_python_from_file(bundled, log)

    if not allow_online:
        log(
            "FEHLER: Kein Offline-Python-Installer im Setup-Bundle "
            f"(erwartet: offline/{PY_OFFLINE_NAME}).\n"
        )
        return False

    if winget_available():
        log("Installiere Python 3.12 ueber winget …\n")
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
        if ok and wait_for_usable_python(log):
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
    return _install_python_from_file(dest, log)


def find_cloudflared() -> Path | None:
    if DEFAULT_CF_EXE.is_file():
        return DEFAULT_CF_EXE
    p = shutil.which("cloudflared")
    return Path(p) if p else None


def install_cloudflared(log: callable, allow_online: bool = False) -> bool:
    found = find_cloudflared()
    if found:
        log(f"cloudflared bereits vorhanden: {found}\n")
        return True

    bundled = bundled_cloudflared()
    if bundled:
        dest_dir = Path(r"C:\Program Files\cloudflared")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "cloudflared.exe"
        shutil.copy2(bundled, dest)
        log(f"cloudflared aus Offline-Bundle kopiert: {dest}\n")
        return dest.is_file()

    if not allow_online:
        log(
            "FEHLER: cloudflared.exe fehlt im Offline-Bundle "
            "und Online-Nachzug ist deaktiviert.\n"
        )
        return False

    if winget_available():
        log("Installiere cloudflared ueber winget …\n")
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
    url = (
        "https://github.com/cloudflare/cloudflared/releases/"
        "latest/download/cloudflared-windows-amd64.exe"
    )
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


def install_python_packages(
    venv_python: Path,
    requirements: Path,
    log: callable,
    allow_online: bool = False,
) -> bool:
    """pip install in venv – bevorzugt lokale Wheels (kein Internet)."""
    pip = venv_python.parent / "pip.exe"
    if not pip.is_file():
        # venv ohne pip reparieren
        log("pip fehlt im venv – ensurepip …\n")
        r = subprocess.run(
            [str(venv_python), "-m", "ensurepip", "--upgrade"],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=_win_no_window(),
        )
        if r.returncode != 0 or not pip.is_file():
            log(f"ensurepip fehlgeschlagen: {(r.stderr or r.stdout or '').strip()}\n")
            return False
    if not requirements.is_file():
        log(f"requirements.txt fehlt: {requirements}\n")
        return False

    wheels = bundled_wheels_dir()
    if wheels:
        log(f"Installiere Abhaengigkeiten offline aus {wheels} …\n")
        # Explizit die bekannten Pakete + requirements, falls colorama noetig
        cmd = [
            str(pip),
            "install",
            "--no-index",
            "--find-links",
            str(wheels),
            "--upgrade",
            "-r",
            str(requirements),
        ]
        if not _run_logged(cmd, log, timeout=600):
            return False
        return True

    if not allow_online:
        log(
            "FEHLER: Keine Offline-Wheels gefunden (offline/wheels).\n"
        )
        return False

    log("Installiere Abhaengigkeiten online (pip) …\n")
    return _run_logged(
        [str(pip), "install", "-r", str(requirements)],
        log,
        timeout=600,
    )


def python_version_label() -> str:
    p = find_python()
    offline = bundled_python_installer()
    suffix = " – Offline-Bundle bereit" if offline else ""
    if not p:
        if offline:
            return f"nicht installiert{suffix} (wird offline mitinstalliert)"
        return "nicht gefunden (kein Offline-Bundle)"
    try:
        r = subprocess.run(
            [str(p), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_win_no_window(),
        )
        ver = (r.stdout or r.stderr or "").strip()
        return f"{ver} – {p}{suffix}"
    except (OSError, subprocess.SubprocessError):
        return str(p)


def cloudflared_version_label() -> str:
    p = find_cloudflared()
    bundled = bundled_cloudflared()
    if not p:
        if bundled:
            return "nicht installiert – Offline-Bundle bereit"
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


def offline_ready_label() -> str:
    py = bundled_python_installer()
    wh = bundled_wheels_dir()
    parts = []
    parts.append("Python-Installer: ja" if py else "Python-Installer: FEHLT")
    if wh:
        n = len(list(wh.glob("*.whl")))
        parts.append(f"Wheels: ja ({n})")
    else:
        parts.append("Wheels: FEHLT")
    cf = bundled_cloudflared()
    parts.append("cloudflared: ja" if cf else "cloudflared: optional fehlt")
    return " | ".join(parts)
