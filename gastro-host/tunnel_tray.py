"""Windows-Leiste für den gemeinsamen Cloudflare-Tunnel.

Das Symbol zeigt nur den Status. Schließen beendet die Anzeige, nicht den Tunnel.
Start und Stopp rufen dieselben Skripte auf wie das Gastro-System.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from tunnel_status import HOST_DIR, read_tunnel_status

LOG_PATH = HOST_DIR.parent / "data" / "tunnel-tray.log"
CREATE_NO_WINDOW = 0x08000000
ERROR_ALREADY_EXISTS = 183

COLORS = {
    "connected": (47, 157, 90, 255),
    "starting": (212, 168, 83, 255),
    "unknown": (212, 168, 83, 255),
    "stopped": (196, 72, 60, 255),
}


def _icon_image(state: str) -> Image.Image:
    color = COLORS.get(state, COLORS["unknown"])
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, 62, 62), fill=color)
    draw.ellipse((18, 26, 46, 42), fill=(255, 255, 255, 235))
    return image


def _log(text: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(text.rstrip() + "\n")
    except OSError:
        pass


def _single_instance() -> bool:
    handle = ctypes.windll.kernel32.CreateMutexW(
        None, False, "Local\\MpbinCloudflareTunnelTray"
    )
    if not handle or ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return False
    globals()["_TRAY_MUTEX"] = handle
    return True


def _run(script: str) -> None:
    path = HOST_DIR / script
    if not path.is_file():
        _log(f"fehlt: {path}")
        return
    subprocess.Popen(
        ["cmd.exe", "/c", str(path)],
        cwd=str(HOST_DIR),
        creationflags=CREATE_NO_WINDOW,
    )


def _start(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    if read_tunnel_status()["state"] == "connected":
        return
    _run("run-cloudflared.cmd")


def _stop(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    if not read_tunnel_status()["process"]:
        return
    _run("stop-cloudflared.cmd")


def _quit(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    icon.stop()


def _menu() -> pystray.Menu:
    status = read_tunnel_status()
    host_items = [
        pystray.MenuItem(host, None, enabled=False) for host in status["hosts"]
    ]
    return pystray.Menu(
        pystray.MenuItem(status["title"], None, enabled=False),
        pystray.MenuItem(status["detail"], None, enabled=False),
        pystray.Menu.SEPARATOR,
        *host_items,
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Tunnel starten",
            _start,
            enabled=lambda _item: read_tunnel_status()["state"] != "connected",
        ),
        pystray.MenuItem(
            "Tunnel stoppen (App, API, Designer)",
            _stop,
            enabled=lambda _item: bool(read_tunnel_status()["process"]),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Symbol schließen", _quit),
    )


def _watch(icon: pystray.Icon) -> None:
    last = None
    while True:
        try:
            status = read_tunnel_status()
            signature = (status["state"], status["connections"], status["tip"])
            icon.title = status["tip"][:127]
            if signature != last:
                icon.icon = _icon_image(status["state"])
                icon.menu = _menu()
                icon.update_menu()
                last = signature
        except Exception:
            _log(traceback.format_exc())
        time.sleep(2)


def main() -> None:
    if not _single_instance():
        return
    status = read_tunnel_status()
    icon = pystray.Icon(
        "mpbin-tunnel",
        _icon_image(status["state"]),
        status["tip"][:127],
        menu=_menu(),
    )

    def setup(running: pystray.Icon) -> None:
        running.visible = True
        threading.Thread(target=_watch, args=(running,), daemon=True).start()

    _log(f"gestartet {time.strftime('%Y-%m-%d %H:%M:%S')} {status['state']}")
    icon.run(setup)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log(traceback.format_exc())
        sys.exit(1)
