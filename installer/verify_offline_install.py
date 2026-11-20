#!/usr/bin/env python3
"""Offline-Frischinstallations-Checks. Exit 0 = OK."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

INSTALLER = Path(__file__).resolve().parent
REPO = INSTALLER.parent
sys.path.insert(0, str(INSTALLER))

from setup_prereqs import (  # noqa: E402
    _is_usable_python,
    bundled_wheels_dir,
    find_python,
    require_offline_bundle,
)


def fail(msg: str) -> None:
    print("FAIL:", msg)
    sys.exit(1)


def main() -> None:
    print("=== 1) Offline-Bundle ===")
    root = require_offline_bundle()
    wheels = bundled_wheels_dir()
    assert wheels
    names = [p.name.lower() for p in wheels.glob("*.whl")]
    print(f"OK Bundle: {root} ({len(names)} wheels)")
    for need in (
        "flask-",
        "flask_cors-",
        "werkzeug-",
        "markupsafe-",
        "jinja2-",
        "click-",
        "blinker-",
        "itsdangerous-",
        "colorama-",
    ):
        if not any(n.startswith(need) for n in names):
            fail(f"Wheel fehlt: {need}")

    print("=== 2) Inkscape-Schutz ===")
    fake = Path(r"C:\Program Files\Inkscape\bin\python.exe")
    if _is_usable_python(fake):
        fail("Inkscape-Python wurde faelschlich als nutzbar erkannt")
    p = find_python()
    if p and "inkscape" in str(p).lower():
        fail(f"find_python lieferte Inkscape: {p}")
    if p and "windowsapps" in str(p).lower():
        fail(f"find_python lieferte Store-Stub: {p}")
    print("python_ok", p)
    print("INKSCAPE_GUARD_OK")

    print("=== 3) Offline venv + Flask ===")
    test_root = Path(tempfile.gettempdir()) / f"gastro-offline-verify-{uuid.uuid4().hex[:8]}"
    try:
        test_root.mkdir(parents=True)
        venv = test_root / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv)],
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        pip = venv / "Scripts" / "pip.exe"
        vpy = venv / "Scripts" / "python.exe"
        req = REPO / "requirements.txt"
        r = subprocess.run(
            [
                str(pip),
                "install",
                "--no-index",
                "--find-links",
                str(wheels),
                "--upgrade",
                "-r",
                str(req),
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if r.returncode != 0:
            fail("pip --no-index fehlgeschlagen:\n" + (r.stderr or r.stdout or ""))
        r2 = subprocess.run(
            [
                str(vpy),
                "-c",
                "import flask, flask_cors; from flask import Flask; print('FLASK_OK')",
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if r2.returncode != 0:
            fail("Flask-Import fehlgeschlagen:\n" + (r2.stderr or r2.stdout or ""))
        print((r2.stdout or "").strip())
    finally:
        shutil.rmtree(test_root, ignore_errors=True)

    print("=== 4) Payload-Dateien ===")
    for rel in (
        "backend/main.py",
        "deploy/frontend_server.py",
        "gastro-host/control_panel.py",
        "gastro-host/run-backend.cmd",
        "gastro-host/run-frontend.cmd",
        "gastro-host/run-control-panel.cmd",
        "gastro-host/prepare-lan.ps1",
        "gastro-host/uninstall.cmd",
        "gastro-host/uninstall.ps1",
        "frontend/api_base.js",
        "requirements.txt",
    ):
        if not (REPO / rel).is_file():
            fail(f"Payload fehlt: {rel}")
    # Kein PATH-Fallback auf pythonw (Inkscape-Falle)
    rcp = (REPO / "gastro-host" / "run-control-panel.cmd").read_text(
        encoding="utf-8", errors="ignore"
    )
    if re.search(r'PYW=pythonw', rcp):
        fail("run-control-panel.cmd faellt noch auf PATH-pythonw zurueck")
    if "venv\\Scripts\\pythonw.exe" not in rcp:
        fail("run-control-panel.cmd nutzt nicht venv\\Scripts\\pythonw.exe")
    rb = (REPO / "gastro-host" / "run-backend.cmd").read_text(
        encoding="utf-8", errors="ignore"
    )
    if "venv\\Scripts\\python.exe" not in rb:
        fail("run-backend.cmd nutzt nicht venv\\Scripts\\python.exe")
    print("OK Payload-Kern + Startskripte ohne PATH-Python")
    print("")
    print("ALLE OFFLINE-CHECKS BESTANDEN")


if __name__ == "__main__":
    main()
