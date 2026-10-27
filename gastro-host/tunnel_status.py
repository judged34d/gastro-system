"""Tunnelstatus nur für dieses Gastro-System.

Control Panel und Leisten-Symbol lesen dieselbe Funktion. Gezählt wird nur
der Prozess, der die eigene cloudflared-Konfiguration geladen hat.
"""
from __future__ import annotations

import re
import subprocess
import urllib.request
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parent
CONFIG_CMD = HOST_DIR / "config.cmd"
METRICS_RE = re.compile(
    r"Starting metrics server on (127\.0\.0\.1:\d+)/metrics"
)
HA_RE = re.compile(
    r"^cloudflared_tunnel_ha_connections(?:\{[^}]*\})?\s+([0-9.]+)\s*$",
    re.M,
)
CREATE_NO_WINDOW = 0x08000000


def _config() -> dict[str, str]:
    out: dict[str, str] = {}
    if not CONFIG_CMD.is_file():
        return out
    try:
        lines = CONFIG_CMD.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line.lower().startswith("set ") or "=" not in line:
            continue
        body = line[4:].strip()
        key, _, val = body.partition("=")
        out[key.strip().strip('"').upper()] = val.strip().strip('"')
    return out


def _expand(value: str, cfg: dict[str, str]) -> str:
    root = cfg.get("GASTRO_ROOT", "")
    return value.replace("%GASTRO_ROOT%", root)


def _hosts(cfg: dict[str, str]) -> list[str]:
    path = Path(_expand(cfg.get("GASTRO_CLOUDFLARED_CFG", ""), cfg))
    if not path.is_file():
        return []
    hosts: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    for line in text.splitlines():
        stripped = line.strip()
        if "hostname:" not in stripped:
            continue
        host = stripped.split("hostname:", 1)[1].strip().strip('"')
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def _process_running() -> bool:
    command = (
        "if (Get-CimInstance Win32_Process -Filter \"Name='cloudflared.exe'\" | "
        "Where-Object { $_.CommandLine -like '*Gastro-System\\cloudflared\\config.yml*' }) "
        "{ exit 0 } else { exit 1 }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


def _metrics_base(cfg: dict[str, str]) -> str:
    root = cfg.get("GASTRO_ROOT") or str(HOST_DIR.parent)
    log_path = Path(root) / "data" / "cloudflared.log"
    port = "127.0.0.1:20241"
    try:
        with log_path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 120_000))
            tail = handle.read().decode("utf-8", errors="ignore")
    except OSError:
        tail = ""
    marker = tail.rfind("cloudflared start")
    section = tail[marker:] if marker >= 0 else tail
    found = METRICS_RE.findall(section)
    if found:
        port = found[-1]
    return f"http://{port}/metrics"


def _connections(cfg: dict[str, str]) -> int | None:
    try:
        with urllib.request.urlopen(_metrics_base(cfg), timeout=0.6) as response:
            text = response.read().decode("utf-8", errors="ignore")
    except (OSError, ValueError):
        return None
    match = HA_RE.search(text)
    if not match:
        return None
    return int(float(match.group(1)))


def read_tunnel_status() -> dict:
    cfg = _config()
    hosts = _hosts(cfg)
    short = [host.removesuffix(".mpbin.de") for host in hosts]
    names = ", ".join(short) if short else "keine Adressen"
    running = _process_running()
    if not running:
        title = "Tunnel gestoppt"
        return {
            "state": "stopped",
            "title": title,
            "detail": "gestoppt",
            "connections": 0,
            "process": False,
            "hosts": hosts,
            "tip": f"{title} · {names}",
        }
    connections = _connections(cfg)
    if connections is None:
        title = "Tunnel unklar"
        return {
            "state": "unknown",
            "title": title,
            "detail": "Prozess läuft, Messung fehlt",
            "connections": 0,
            "process": True,
            "hosts": hosts,
            "tip": f"{title} · {names}",
        }
    if connections > 0:
        title = "Tunnel verbunden"
        detail = f"verbunden · {connections} Verbindungen"
        return {
            "state": "connected",
            "title": title,
            "detail": detail,
            "connections": connections,
            "process": True,
            "hosts": hosts,
            "tip": f"{title} · {connections} · {names}",
        }
    title = "Tunnel startet"
    return {
        "state": "starting",
        "title": title,
        "detail": "startet",
        "connections": 0,
        "process": True,
        "hosts": hosts,
        "tip": f"{title} · {names}",
    }
