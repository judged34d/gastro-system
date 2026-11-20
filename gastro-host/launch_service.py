#!/usr/bin/env python3
"""Zuverlaessiger Dienst-Start: generiert kurze .bat und startet sie versteckt."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parent
ROOT = HOST_DIR.parent
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def _log_startup(msg: str) -> None:
    data = ROOT / "data"
    data.mkdir(parents=True, exist_ok=True)
    with (data / "startup.log").open("a", encoding="utf-8", errors="replace") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def _read_config_cmd() -> dict[str, str]:
    out: dict[str, str] = {}
    cfg = HOST_DIR / "config.cmd"
    if not cfg.is_file():
        return out
    for line in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line.lower().startswith("set "):
            continue
        body = line[4:].strip()
        if body.startswith('"') and body.endswith('"'):
            body = body[1:-1]
        if "=" not in body:
            continue
        key, _, val = body.partition("=")
        out[key.strip().upper()] = val.strip().strip('"')
    # config.cmd speichert oft %GASTRO_ROOT% – hier aufgeloest, sonst DB-Pfad kaputt
    root = out.get("GASTRO_ROOT") or str(ROOT)
    for key, val in list(out.items()):
        if "%GASTRO_ROOT%" in val:
            out[key] = val.replace("%GASTRO_ROOT%", root)
    out.setdefault("GASTRO_ROOT", root)
    return out


def _port_listening(port: int) -> bool:
    try:
        r = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        needle = f":{port}"
        for line in (r.stdout or "").splitlines():
            if needle not in line:
                continue
            low = line.lower()
            # DE: ABHOREN / ABHÖREN gekürzt oft als ABH…; EN: LISTENING
            if "listening" in low or "abh" in low:
                return True
    except (OSError, subprocess.SubprocessError):
        pass
    return False


def _venv_python() -> Path:
    py = ROOT / "venv" / "Scripts" / "python.exe"
    if not py.is_file():
        raise FileNotFoundError(f"venv Python fehlt: {py}")
    low = str(py).lower().replace("/", "\\")
    if "inkscape" in low or "windowsapps" in low:
        raise RuntimeError(f"Ungueltiger Python-Pfad: {py}")
    return py


def _write_bat(path: Path, lines: list[str]) -> None:
    path.write_text("\r\n".join(lines) + "\r\n", encoding="ascii", errors="replace")


def launch(service: str) -> int:
    cfg = _read_config_cmd()
    data = ROOT / "data"
    data.mkdir(parents=True, exist_ok=True)

    try:
        py = _venv_python()
    except (FileNotFoundError, RuntimeError) as exc:
        _log_startup(f"FAIL {service}: {exc}")
        return 1

    pre = subprocess.run(
        [str(py), "-c", "import flask, flask_cors; print('ok')"],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=CREATE_NO_WINDOW,
    )
    if pre.returncode != 0:
        _log_startup(
            f"FAIL {service}: Flask fehlt im venv – "
            f"{(pre.stderr or pre.stdout or '').strip()}"
        )
        return 2

    if service == "backend":
        port = int(cfg.get("GASTRO_BACKEND_PORT") or "8000")
        cwd = ROOT / "backend"
        script = cwd / "main.py"
        log_path = data / "backend.log"
        bat_path = data / "_run_backend.bat"
        gastro_root = cfg.get("GASTRO_ROOT") or str(ROOT)
        raw_db = cfg.get("GASTRO_DB_PATH") or str(data / "database.db")
        db_path = str(Path(raw_db).resolve())
        # Parent-Ordner sicherstellen (frisch installiert / leeres data)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        env_lines = [
            f'set "GASTRO_ROOT={gastro_root}"',
            f'set "GASTRO_DB_PATH={db_path}"',
            f'set "GASTRO_BACKEND_PORT={port}"',
            'set "PYTHONUNBUFFERED=1"',
        ]
    elif service == "frontend":
        port = int(cfg.get("GASTRO_FRONTEND_PORT") or "8081")
        cwd = ROOT
        script = ROOT / "deploy" / "frontend_server.py"
        log_path = data / "frontend.log"
        bat_path = data / "_run_frontend.bat"
        env_lines = [
            f'set "FRONTEND_PORT={port}"',
            'set "PYTHONUNBUFFERED=1"',
        ]
    else:
        _log_startup(f"FAIL unknown service: {service}")
        return 3

    if _port_listening(port):
        _log_startup(f"OK {service} already on :{port}")
        return 0

    if not script.is_file():
        _log_startup(f"FAIL {service}: script fehlt {script}")
        return 4

    # Kurzes .bat = zuverlaessigste Windows-Umleitung in Logdatei
    bat_lines = [
        "@echo off",
        f'cd /d "{cwd}"',
        *env_lines,
        f'"{py}" -u "{script}" >>"{log_path}" 2>&1',
    ]
    _write_bat(bat_path, bat_lines)
    _log_startup(f"START {service} via {bat_path}")

    try:
        with log_path.open("a", encoding="utf-8", errors="replace") as logf:
            logf.write(
                f"\n===== launch {service} "
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
            )
        # start erzeugt eigenen Prozessbaum; /MIN versteckt Fenster nicht immer –
        # deshalb start "" /B unter cmd
        # bat laeuft eigenstaendig weiter (python >> log); dieser Prozess wartet nur auf Port
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat_path)],
            cwd=str(cwd),
            creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
        )
    except OSError as exc:
        _log_startup(f"FAIL {service} Popen: {exc}")
        return 5

    for i in range(40):
        time.sleep(0.25)
        if _port_listening(port):
            _log_startup(f"OK {service} listening :{port} after {(i + 1) * 0.25:.1f}s")
            return 0

    # Letzte Logzeilen anhaengen
    try:
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
        _log_startup(f"WARN {service}: kein LISTEN :{port}. Log-Ende:\n" + "\n".join(tail))
    except OSError:
        _log_startup(f"WARN {service}: kein LISTEN :{port}")
    return 6


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("backend", "frontend"):
        print("Usage: launch_service.py backend|frontend", file=sys.stderr)
        return 9
    try:
        return launch(sys.argv[1])
    except Exception as exc:
        _log_startup(f"FAIL exception: {exc}")
        return 8


if __name__ == "__main__":
    raise SystemExit(main())
