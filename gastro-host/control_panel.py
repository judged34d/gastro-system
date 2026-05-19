#!/usr/bin/env python3
"""Gastro-System – minimales Control Panel (Start / Tunnel / Stop + Live-Status)."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import ttk

HOST_DIR = Path(__file__).resolve().parent
BACKEND_PORT = 8000
FRONTEND_PORT = 8081
REFRESH_MS = 2000


def run_cmd(name: str) -> None:
    path = HOST_DIR / name
    if not path.is_file():
        return
    subprocess.Popen(
        ["cmd.exe", "/c", str(path)],
        cwd=str(HOST_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def http_ok(url: str, timeout: float = 2.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def backend_health() -> tuple[bool, bool]:
    """(api_ok, db_ok)"""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{BACKEND_PORT}/health", timeout=2.5
        ) as r:
            if r.status != 200:
                return False, False
            data = json.loads(r.read().decode("utf-8"))
            return bool(data.get("ok")), bool(data.get("db"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return False, False


def cloudflared_running() -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq cloudflared.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return "cloudflared.exe" in (out.stdout or "").lower()
    except (OSError, subprocess.SubprocessError):
        return False


class GastroPanel:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Gastro-System")
        self.root.resizable(False, False)
        self.root.geometry("420x320")
        self._build()
        self._tick()

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}
        ttk.Label(self.root, text="Gastro-System", font=("Segoe UI", 14, "bold")).pack(
            anchor=tk.W, **pad
        )

        self.status = tk.Text(
            self.root, height=10, width=48, font=("Consolas", 10), state=tk.DISABLED
        )
        self.status.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        ttk.Button(
            self.root,
            text="Gastro-System starten",
            command=self._start_gastro,
        ).pack(fill=tk.X, **pad)
        ttk.Button(
            self.root,
            text="Online Tunnel verbinden",
            command=self._start_tunnel,
        ).pack(fill=tk.X, **pad)
        ttk.Button(
            self.root,
            text="Gastro-System stoppen",
            command=self._stop_all,
        ).pack(fill=tk.X, **pad)

    def _set_status(self, lines: list[str]) -> None:
        self.status.configure(state=tk.NORMAL)
        self.status.delete("1.0", tk.END)
        self.status.insert(tk.END, "\n".join(lines))
        self.status.configure(state=tk.DISABLED)

    def _live_lines(self) -> list[str]:
        api_ok, db_ok = backend_health()
        fe_ok = http_ok(f"http://127.0.0.1:{FRONTEND_PORT}/health.json")
        cf_ok = cloudflared_running()

        def mark(ok: bool) -> str:
            return "OK" if ok else "offline"

        return [
            "Live-Status",
            f"  Backend API  :{BACKEND_PORT}  {mark(api_ok)}",
            f"  Datenbank    :           {mark(db_ok)}",
            f"  Frontend UI  :{FRONTEND_PORT}  {mark(fe_ok)}",
            f"  Cloudflared  :           {mark(cf_ok)}",
        ]

    def _tick(self) -> None:
        self._set_status(self._live_lines())
        self.root.after(REFRESH_MS, self._tick)

    def _start_gastro(self) -> None:
        run_cmd("run-backend.cmd")
        run_cmd("run-frontend.cmd")

    def _start_tunnel(self) -> None:
        run_cmd("run-cloudflared.cmd")

    def _stop_all(self) -> None:
        for name in ("stop-backend.cmd", "stop-frontend.cmd", "stop-cloudflared.cmd"):
            run_cmd(name)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    GastroPanel().run()


if __name__ == "__main__":
    main()
