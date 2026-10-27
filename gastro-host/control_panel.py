#!/usr/bin/env python3
"""Gastro-System Control Panel – Live-Status, Datenfluss, Bestell-Log."""
from __future__ import annotations

import http.client
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from tunnel_status import read_tunnel_status

HOST_DIR = Path(__file__).resolve().parent
CONFIG_CMD = HOST_DIR / "config.cmd"
BACKEND_PORT = 8000
FRONTEND_PORT = 8081
STATUS_INTERVAL_S = 1.5
STARTING_TIMEOUT_S = 90
HTTP_TIMEOUT_S = 0.45
PULSE_ANIM_MS = 200

COLOR = {
    "bg": "#121812",
    "panel": "#1a221c",
    "text": "#f4f7f5",
    "muted": "#9aab9f",
    "ok": "#2f9d5a",
    "warn": "#d4a853",
    "err": "#e85d4f",
    "off": "#4a554c",
    "accent": "#3d8fd9",
    "log_bg": "#0d120e",
    "btn": "#2a6f2a",
    "btn_stop": "#8b3a3a",
    "btn_tunnel": "#1f5f9c",
}


def _read_host_config() -> dict[str, str]:
    out: dict[str, str] = {}
    if not CONFIG_CMD.is_file():
        return out
    try:
        for line in CONFIG_CMD.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line.lower().startswith("set "):
                continue
            body = line[4:].strip()
            if "=" not in body:
                continue
            key, _, val = body.partition("=")
            out[key.strip().strip('"').upper()] = val.strip().strip('"')
    except OSError:
        pass
    return out


def run_cmd(name: str) -> None:
    path = HOST_DIR / name
    if not path.is_file():
        return
    subprocess.Popen(
        ["cmd.exe", "/c", str(path)],
        cwd=str(HOST_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def http_json(url: str, timeout: float = HTTP_TIMEOUT_S) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            if not (200 <= r.status < 400):
                return None
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None


def http_ok(url: str, timeout: float = HTTP_TIMEOUT_S) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def backend_health() -> tuple[bool, bool]:
    data = http_json(f"http://127.0.0.1:{BACKEND_PORT}/health")
    if not data:
        return False, False
    return bool(data.get("ok")), bool(data.get("db"))


def detect_lan_ips() -> list[str]:
    """IPv4-Adressen dieses PCs (ohne Loopback/APIPA/Host-Only), für LAN-Hinweis."""
    preferred: list[str] = []
    others: list[str] = []
    try:
        out = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW,
            encoding="oem",
            errors="ignore",
        )
        skip = False
        has_gateway = False
        pending_ip: str | None = None

        def flush() -> None:
            nonlocal pending_ip, has_gateway
            if pending_ip:
                target = preferred if has_gateway else others
                if pending_ip not in preferred and pending_ip not in others:
                    target.append(pending_ip)
            pending_ip = None
            has_gateway = False

        for raw in (out.stdout or "").splitlines():
            line = raw.strip()
            low = line.lower()
            if not line:
                continue
            if "adapter" in low or (
                line.endswith(":") and "adresse" not in low and "address" not in low
            ):
                flush()
                skip = any(
                    x in low
                    for x in ("virtualbox", "loopback", "vethernet", "hyper-v", "docker")
                )
                continue
            if skip:
                continue
            if "ipv4" in low and ":" in line:
                addr = line.split(":")[-1].strip()
                if (
                    addr
                    and not addr.startswith("127.")
                    and not addr.startswith("169.254.")
                    and not addr.startswith("192.168.56.")  # typ. VirtualBox Host-Only
                ):
                    pending_ip = addr
            elif ("standardgateway" in low or "default gateway" in low) and ":" in line:
                gw = line.split(":")[-1].strip()
                if gw and gw not in (".", ""):
                    has_gateway = True
        flush()
    except (OSError, subprocess.SubprocessError):
        pass
    ips = preferred + [ip for ip in others if ip not in preferred]
    cfg_ip = _read_host_config().get("GASTRO_LAN_IP", "").strip()
    if cfg_ip and cfg_ip != "127.0.0.1" and cfg_ip not in ips:
        ips.insert(0, cfg_ip)
    return ips


class GastroPanel:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Gastro-System Control")
        self.root.geometry("720x580")
        self.root.minsize(640, 520)
        self.root.configure(bg=COLOR["bg"])

        self._phase = "stopped"
        self._starting_since: float | None = None
        self._data_pulse_until = 0.0
        self._log_since_id = 0
        self._pulse_on = False
        self._stop_threads = False
        self._stream_connected = False
        self._status_lock = threading.Lock()
        self._pending_status: dict | None = None
        self._lan_hint_at = 0.0

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_style()
        self._build()
        self._start_status_worker()
        self._start_activity_stream()
        self._tick_ui()

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=COLOR["bg"])
        style.configure("Card.TFrame", background=COLOR["panel"])
        style.configure(
            "Title.TLabel",
            background=COLOR["bg"],
            foreground=COLOR["text"],
            font=("Segoe UI", 16, "bold"),
        )
        style.configure(
            "Muted.TLabel",
            background=COLOR["bg"],
            foreground=COLOR["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Card.TLabel",
            background=COLOR["panel"],
            foreground=COLOR["text"],
            font=("Segoe UI", 11),
        )
        style.configure(
            "CardMuted.TLabel",
            background=COLOR["panel"],
            foreground=COLOR["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Phase.TLabel",
            background=COLOR["panel"],
            foreground=COLOR["text"],
            font=("Segoe UI", 13, "bold"),
        )
        style.configure("TNotebook", background=COLOR["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=COLOR["panel"],
            foreground=COLOR["text"],
            padding=(14, 8),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLOR["ok"])],
            foreground=[("selected", "#fff")],
        )

    def _build(self) -> None:
        # Aktionsleiste ZUERST unten fixieren – immer sichtbar
        self._build_actions()

        head = ttk.Frame(self.root)
        head.pack(fill=tk.X, padx=16, pady=(14, 6))
        ttk.Label(head, text="Gastro-System", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            head,
            text="Control Panel · Live-Status & Bestell-Log",
            style="Muted.TLabel",
        ).pack(anchor=tk.W)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 8))

        self.tab_status = ttk.Frame(self.nb)
        self.tab_log = ttk.Frame(self.nb)
        self.nb.add(self.tab_status, text="  Übersicht  ")
        self.nb.add(self.tab_log, text="  Live-Log  ")

        self._build_status_tab()
        self._build_log_tab()

    def _build_actions(self) -> None:
        actions = tk.Frame(self.root, bg=COLOR["bg"])
        actions.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 14))

        self.btn_start = tk.Button(
            actions,
            text="Gastro-System starten",
            command=self._start_gastro,
            bg=COLOR["btn"],
            fg="#fff",
            activebackground="#3a9a3a",
            activeforeground="#fff",
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=12,
            pady=12,
            cursor="hand2",
        )
        self.btn_start.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        self.btn_tunnel = tk.Button(
            actions,
            text="Tunnel starten",
            command=self._start_tunnel,
            bg=COLOR["btn_tunnel"],
            fg="#fff",
            activebackground="#2a7ec8",
            activeforeground="#fff",
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=12,
            pady=12,
            cursor="hand2",
        )
        self.btn_tunnel.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)

        self.btn_stop = tk.Button(
            actions,
            text="Stoppen",
            command=self._stop_all,
            bg=COLOR["btn_stop"],
            fg="#fff",
            activebackground="#a04040",
            activeforeground="#fff",
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=12,
            pady=12,
            cursor="hand2",
        )
        self.btn_stop.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(6, 0))

    def _build_status_tab(self) -> None:
        card = ttk.Frame(self.tab_status, style="Card.TFrame")
        card.pack(fill=tk.X, padx=8, pady=8)

        top = ttk.Frame(card, style="Card.TFrame")
        top.pack(fill=tk.X, padx=14, pady=12)

        self.phase_dot = tk.Canvas(
            top, width=22, height=22, bg=COLOR["panel"], highlightthickness=0
        )
        self.phase_dot.pack(side=tk.LEFT)
        self._draw_dot(self.phase_dot, COLOR["off"])

        self.phase_label = ttk.Label(top, text="Gestoppt", style="Phase.TLabel")
        self.phase_label.pack(side=tk.LEFT, padx=(10, 0))

        pulse_wrap = ttk.Frame(top, style="Card.TFrame")
        pulse_wrap.pack(side=tk.RIGHT)
        ttk.Label(pulse_wrap, text="Datenfluss", style="CardMuted.TLabel").pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self.data_dot = tk.Canvas(
            pulse_wrap, width=18, height=18, bg=COLOR["panel"], highlightthickness=0
        )
        self.data_dot.pack(side=tk.LEFT)
        self._draw_dot(self.data_dot, COLOR["off"])

        grid = ttk.Frame(card, style="Card.TFrame")
        grid.pack(fill=tk.X, padx=14, pady=(0, 14))

        self.row_vars = {}
        for key, title in (
            ("backend", "Backend API"),
            ("db", "Datenbank"),
            ("frontend", "Frontend UI"),
            ("tunnel", "Online-Tunnel"),
        ):
            row = ttk.Frame(grid, style="Card.TFrame")
            row.pack(fill=tk.X, pady=4)
            canvas = tk.Canvas(
                row, width=14, height=14, bg=COLOR["panel"], highlightthickness=0
            )
            canvas.pack(side=tk.LEFT)
            self._draw_dot(canvas, COLOR["off"])
            ttk.Label(row, text=title, style="Card.TLabel", width=16).pack(
                side=tk.LEFT, padx=(8, 0)
            )
            detail = ttk.Label(row, text="—", style="CardMuted.TLabel")
            detail.pack(side=tk.LEFT, padx=(8, 0))
            self.row_vars[key] = {"dot": canvas, "detail": detail}

        lan_card = ttk.Frame(self.tab_status, style="Card.TFrame")
        lan_card.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(
            lan_card,
            text="Offline / LAN-Zugriff (Fritzbox-WLAN)",
            style="Card.TLabel",
        ).pack(anchor=tk.W, padx=14, pady=(12, 4))
        self.lan_label = ttk.Label(
            lan_card,
            text="LAN-IP wird ermittelt…",
            style="CardMuted.TLabel",
            wraplength=640,
            justify=tk.LEFT,
        )
        self.lan_label.pack(anchor=tk.W, padx=14, pady=(0, 12))
        self._refresh_lan_hint()

        ttk.Label(
            self.tab_status,
            text="Stoppen beendet nur das Gastro-System. Der Tunnel bleibt für den Designer offen. Derselbe Status steht im Windows-Infobereich.",
            style="Muted.TLabel",
            wraplength=640,
        ).pack(anchor=tk.W, padx=12, pady=(4, 8))

    def _build_log_tab(self) -> None:
        wrap = ttk.Frame(self.tab_log)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        bar = ttk.Frame(wrap)
        bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(
            bar,
            text="Laufende Bestell- und Statusmeldungen",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT)
        tk.Button(
            bar,
            text="Log leeren",
            command=self._clear_log_view,
            bg=COLOR["panel"],
            fg=COLOR["text"],
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.RIGHT)

        self.log = tk.Text(
            wrap,
            font=("Consolas", 10),
            bg=COLOR["log_bg"],
            fg=COLOR["text"],
            insertbackground=COLOR["text"],
            relief=tk.FLAT,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        scroll = ttk.Scrollbar(wrap, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.log.tag_configure("ts", foreground=COLOR["muted"])
        self.log.tag_configure("order", foreground="#7dcea0")
        self.log.tag_configure("prep", foreground="#85c1e9")
        self.log.tag_configure("ready", foreground="#f5b041")
        self.log.tag_configure("paid", foreground="#58d68d")
        self.log.tag_configure("other", foreground=COLOR["text"])

    def _draw_dot(self, canvas: tk.Canvas, color: str) -> None:
        canvas.delete("all")
        w = int(canvas["width"])
        h = int(canvas["height"])
        pad = 2
        canvas.create_oval(pad, pad, w - pad, h - pad, fill=color, outline="")

    def _set_row(
        self,
        key: str,
        ok: bool,
        detail: str,
        warn: bool = False,
        independent: bool = False,
    ) -> None:
        color = COLOR["ok"] if ok else (COLOR["warn"] if warn else COLOR["err"])
        if not independent and self._phase == "stopped" and not ok:
            color = COLOR["off"]
        self._draw_dot(self.row_vars[key]["dot"], color)
        self.row_vars[key]["detail"].configure(text=detail)

    def _refresh_lan_hint(self) -> None:
        ips = detect_lan_ips()
        cfg = _read_host_config()
        cf_on = cfg.get("GASTRO_CLOUDFLARED_ENABLED", "0") != "0"
        if not ips:
            text = (
                f"Keine LAN-IP gefunden. Nach Anschluss an die Fritzbox "
                f"als Admin ausführen:\n"
                f"gastro-host\\prepare-lan.ps1\n"
                f"Lokal: http://127.0.0.1:{FRONTEND_PORT}/"
            )
        else:
            primary = ips[0]
            lines = [
                f"Tablets/Handys (gleiches WLAN):  http://{primary}:{FRONTEND_PORT}/",
                f"API-Check:  http://{primary}:{BACKEND_PORT}/health",
            ]
            if len(ips) > 1:
                lines.append("Weitere IPs: " + ", ".join(ips[1:]))
            lines.append(
                "QR-Codes im Admin über diese LAN-URL drucken (nicht app.mpbin.de)."
            )
            if cf_on:
                lines.append(
                    "Der Tunnel ist unabhängig vom Gastro-Start. Sein Status steht in der Leiste."
                )
            text = "\n".join(lines)
        self.lan_label.configure(text=text)

    def _set_phase(self, phase: str, label: str, color: str) -> None:
        self._phase = phase
        self.phase_label.configure(text=label)
        self._draw_dot(self.phase_dot, color)

    def _append_log(self, event: dict) -> None:
        kind = event.get("kind") or "other"
        created = str(event.get("created_at") or "").replace("T", " ")
        if len(created) > 19:
            created = created[:19]
        msg = event.get("message") or ""
        tag = {
            "order_created": "order",
            "order_preparing": "prep",
            "order_ready": "ready",
            "order_paid": "paid",
        }.get(kind, "other")

        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, f"[{created}] ", "ts")
        self.log.insert(tk.END, msg + "\n", tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _clear_log_view(self) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _on_activity_event(self, event: dict) -> None:
        eid = int(event.get("id") or 0)
        if eid and eid <= self._log_since_id:
            return
        if eid:
            self._log_since_id = max(self._log_since_id, eid)
        self._append_log(event)
        self._data_pulse_until = time.time() + 2.0

    def _collect_status(self) -> dict:
        api_ok, db_ok = backend_health()
        fe_ok = http_ok(f"http://127.0.0.1:{FRONTEND_PORT}/health.json")
        tunnel = read_tunnel_status()
        return {
            "api_ok": api_ok,
            "db_ok": db_ok,
            "fe_ok": fe_ok,
            "cf_ok": tunnel["state"] == "connected",
            "tunnel": tunnel,
        }

    def _start_status_worker(self) -> None:
        def worker() -> None:
            while not self._stop_threads:
                try:
                    snap = self._collect_status()
                    with self._status_lock:
                        self._pending_status = snap
                except Exception:
                    pass
                time.sleep(STATUS_INTERVAL_S)

        threading.Thread(
            target=worker, name="gastro-status", daemon=True
        ).start()

    def _apply_status(self, snap: dict) -> None:
        api_ok = bool(snap.get("api_ok"))
        db_ok = bool(snap.get("db_ok"))
        fe_ok = bool(snap.get("fe_ok"))
        cf_ok = bool(snap.get("cf_ok"))
        tunnel = snap.get("tunnel") or {}
        tunnel_state = str(tunnel.get("state") or "stopped")

        self._set_row(
            "backend",
            api_ok,
            f":{BACKEND_PORT}  {'online' if api_ok else 'offline'}",
        )
        self._set_row("db", db_ok, "verbunden" if db_ok else "offline")
        self._set_row(
            "frontend",
            fe_ok,
            f":{FRONTEND_PORT}  {'online' if fe_ok else 'offline'}",
        )
        self._set_row(
            "tunnel",
            tunnel_state == "connected",
            str(tunnel.get("detail") or "gestoppt"),
            warn=tunnel_state in ("starting", "unknown"),
            independent=True,
        )
        self._apply_tunnel_button(tunnel_state)

        core_ok = api_ok and db_ok and fe_ok
        any_up = api_ok or fe_ok

        if self._starting_since is not None:
            elapsed = time.time() - self._starting_since
            if core_ok:
                self._starting_since = None
                self._set_phase("running", "Gestartet", COLOR["ok"])
            elif elapsed > STARTING_TIMEOUT_S:
                self._starting_since = None
                self._set_phase("error", "Fehler beim Start (Timeout)", COLOR["err"])
            else:
                self._set_phase(
                    "starting", f"Hochfahren… ({int(elapsed)}s)", COLOR["warn"]
                )
        elif core_ok:
            label = "Gestartet (LAN)" if not cf_ok else "Gestartet (Online)"
            self._set_phase("running", label, COLOR["ok"])
            if not hasattr(self, "_lan_hint_at") or time.time() - self._lan_hint_at > 20:
                self._lan_hint_at = time.time()
                self._refresh_lan_hint()
        elif any_up:
            self._set_phase("partial", "Teilweise gestartet", COLOR["warn"])
        else:
            self._set_phase("stopped", "Gestoppt", COLOR["off"])

    def _tick_ui(self) -> None:
        if self._stop_threads:
            return

        with self._status_lock:
            snap = self._pending_status
            self._pending_status = None
        if snap:
            self._apply_status(snap)

        now = time.time()
        if now < self._data_pulse_until:
            self._pulse_on = not self._pulse_on
            self._draw_dot(
                self.data_dot, COLOR["accent"] if self._pulse_on else COLOR["ok"]
            )
        else:
            color = COLOR["ok"] if self._stream_connected else COLOR["off"]
            self._draw_dot(self.data_dot, color)

        self.root.after(PULSE_ANIM_MS, self._tick_ui)

    def _start_activity_stream(self) -> None:
        threading.Thread(
            target=self._activity_stream_loop,
            name="gastro-activity-sse",
            daemon=True,
        ).start()

    def _activity_stream_loop(self) -> None:
        while not self._stop_threads:
            try:
                conn = http.client.HTTPConnection(
                    "127.0.0.1", BACKEND_PORT, timeout=60
                )
                path = f"/activity/stream?since_id={self._log_since_id}"
                conn.request(
                    "GET",
                    path,
                    headers={
                        "Accept": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
                resp = conn.getresponse()
                if resp.status != 200:
                    conn.close()
                    self._stream_connected = False
                    time.sleep(1.2)
                    continue

                self._stream_connected = True
                buffer = ""
                while not self._stop_threads:
                    chunk = resp.read(256)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n\n" in buffer:
                        block, buffer = buffer.split("\n\n", 1)
                        data_lines = []
                        for line in block.splitlines():
                            if line.startswith("data:"):
                                data_lines.append(line[5:].lstrip())
                        if not data_lines:
                            continue
                        raw = "\n".join(data_lines).strip()
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(event, dict):
                            self.root.after(0, self._on_activity_event, event)
                conn.close()
                self._stream_connected = False
            except (OSError, http.client.HTTPException, ValueError):
                self._stream_connected = False
                time.sleep(1.2)

    def _start_gastro(self) -> None:
        self._starting_since = time.time()
        self._set_phase("starting", "Hochfahren…", COLOR["warn"])
        threading.Thread(
            target=lambda: (run_cmd("run-backend.cmd"), run_cmd("run-frontend.cmd")),
            daemon=True,
        ).start()

    def _tunnel_unchanged(self) -> None:
        return

    def _apply_tunnel_button(self, state: str) -> None:
        if state == "connected":
            self.btn_tunnel.configure(
                text="Tunnel verbunden",
                bg=COLOR["ok"],
                fg="#fff",
                state=tk.NORMAL,
                command=self._tunnel_unchanged,
            )
        elif state == "starting":
            self.btn_tunnel.configure(
                text="Tunnel startet…",
                bg=COLOR["warn"],
                fg="#1a221c",
                state=tk.DISABLED,
            )
        elif state == "unknown":
            self.btn_tunnel.configure(
                text="Tunnel unklar",
                bg=COLOR["warn"],
                fg="#1a221c",
                state=tk.NORMAL,
                command=self._tunnel_unchanged,
            )
        else:
            self.btn_tunnel.configure(
                text="Tunnel starten",
                bg=COLOR["btn_tunnel"],
                fg="#fff",
                state=tk.NORMAL,
                command=self._start_tunnel,
            )

    def _start_tunnel(self) -> None:
        if read_tunnel_status()["state"] == "connected":
            return
        threading.Thread(
            target=lambda: run_cmd("run-cloudflared.cmd"), daemon=True
        ).start()

    def _stop_all(self) -> None:
        self._starting_since = None
        self._set_phase("stopped", "Wird gestoppt…", COLOR["warn"])

        def stop() -> None:
            for name in (
                "stop-backend.cmd",
                "stop-frontend.cmd",
            ):
                run_cmd(name)

        threading.Thread(target=stop, daemon=True).start()

    def _on_close(self) -> None:
        self._stop_threads = True
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    GastroPanel().run()


if __name__ == "__main__":
    main()
