#!/usr/bin/env python3
"""Lokaler Bondruck-Agent fuer Stations-Terminals (Ubuntu/Windows).

Laeuft auf dem Geraet, an dem der Bondrucker haengt (z. B. Ubuntu-Theke).
Gastro-Backend oder kitchen.html schicken ESC/POS an http://127.0.0.1:9109/print

Start:
  python3 print_agent.py
  # optional: GASTRO_PRINT_PORT=9109 GASTRO_PRINTER_NAME=HP_A798
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("GASTRO_PRINT_PORT", "9109"))
PRINTER_NAME = (os.environ.get("GASTRO_PRINTER_NAME") or "").strip()
BIND = os.environ.get("GASTRO_PRINT_BIND", "0.0.0.0")


def _list_printers() -> list[str]:
    if os.name == "nt":
        try:
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-Printer | Select-Object -ExpandProperty Name",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            return [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
        except (OSError, subprocess.SubprocessError):
            return []
    try:
        out = subprocess.run(
            ["lpstat", "-a"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        names = []
        for line in (out.stdout or "").splitlines():
            part = line.split()
            if part:
                names.append(part[0])
        return names
    except (OSError, subprocess.SubprocessError):
        return []


def _default_printer() -> str:
    if PRINTER_NAME:
        return PRINTER_NAME
    if os.name == "nt":
        try:
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-Printer | Where-Object Default -eq $true | Select-Object -First 1).Name",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            return (out.stdout or "").strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    try:
        out = subprocess.run(
            ["lpstat", "-d"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # "system default destination: Foo"
        text = out.stdout or ""
        if ":" in text:
            return text.split(":", 1)[1].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    names = _list_printers()
    return names[0] if names else ""


def _print_raw_linux(printer: str, payload: bytes) -> None:
    cmd = ["lp", "-o", "raw"]
    if printer:
        cmd.extend(["-d", printer])
    r = subprocess.run(cmd, input=payload, capture_output=True, timeout=15)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or b"").decode("utf-8", errors="replace")
        raise RuntimeError(err.strip() or f"lp exit {r.returncode}")


def _print_raw_windows(printer: str, payload: bytes) -> None:
    if not printer:
        raise RuntimeError("Kein Windows-Drucker (Standard/Name)")
    try:
        import win32print  # type: ignore

        h = win32print.OpenPrinter(printer)
        try:
            win32print.StartDocPrinter(h, 1, ("GastroOrderBon", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, payload)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        return
    except ImportError:
        pass

    import ctypes
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv")
    OpenPrinter = winspool.OpenPrinterW
    OpenPrinter.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.HANDLE), wintypes.LPVOID]
    OpenPrinter.restype = wintypes.BOOL
    ClosePrinter = winspool.ClosePrinter
    ClosePrinter.argtypes = [wintypes.HANDLE]
    StartDocPrinter = winspool.StartDocPrinterW
    StartDocPrinter.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID]
    StartDocPrinter.restype = wintypes.DWORD
    EndDocPrinter = winspool.EndDocPrinter
    EndDocPrinter.argtypes = [wintypes.HANDLE]
    StartPagePrinter = winspool.StartPagePrinter
    StartPagePrinter.argtypes = [wintypes.HANDLE]
    EndPagePrinter = winspool.EndPagePrinter
    EndPagePrinter.argtypes = [wintypes.HANDLE]
    WritePrinter = winspool.WritePrinter
    WritePrinter.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    WritePrinter.restype = wintypes.BOOL

    class DOC_INFO_1(ctypes.Structure):
        _fields_ = [
            ("pDocName", wintypes.LPCWSTR),
            ("pOutputFile", wintypes.LPCWSTR),
            ("pDatatype", wintypes.LPCWSTR),
        ]

    handle = wintypes.HANDLE()
    if not OpenPrinter(printer, ctypes.byref(handle), None):
        raise RuntimeError(f"OpenPrinter fehlgeschlagen: {printer}")
    try:
        doc = DOC_INFO_1("GastroOrderBon", None, "RAW")
        if not StartDocPrinter(handle, 1, ctypes.byref(doc)):
            raise RuntimeError("StartDocPrinter fehlgeschlagen")
        StartPagePrinter(handle)
        written = wintypes.DWORD(0)
        buf = ctypes.create_string_buffer(payload)
        if not WritePrinter(handle, buf, len(payload), ctypes.byref(written)):
            raise RuntimeError("WritePrinter fehlgeschlagen")
        EndPagePrinter(handle)
        EndDocPrinter(handle)
    finally:
        ClosePrinter(handle)


def print_raw(payload: bytes, printer: str | None = None) -> str:
    name = (printer or "").strip() or _default_printer()
    if os.name == "nt":
        _print_raw_windows(name, payload)
        return f"windows://{name}"
    _print_raw_linux(name, payload)
    return f"cups://{name or 'default'}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[print-agent] " + (fmt % args) + "\n")

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self._json(
                200,
                {
                    "ok": True,
                    "default_printer": _default_printer(),
                    "printers": _list_printers(),
                    "platform": sys.platform,
                },
            )
            return
        if self.path.startswith("/printers"):
            self._json(200, {"printers": _list_printers(), "default": _default_printer()})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self.path.startswith("/print"):
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "invalid json"})
            return
        printer = str(data.get("printer") or "").strip() or None
        payload = b""
        if data.get("escpos_b64"):
            try:
                payload = base64.b64decode(data["escpos_b64"])
            except (TypeError, ValueError):
                self._json(400, {"error": "invalid escpos_b64"})
                return
        elif data.get("escpos_hex"):
            try:
                payload = bytes.fromhex(str(data["escpos_hex"]))
            except ValueError:
                self._json(400, {"error": "invalid escpos_hex"})
                return
        else:
            self._json(400, {"error": "escpos_b64 required"})
            return
        try:
            target = print_raw(payload, printer)
            self._json(200, {"ok": True, "target": target})
        except Exception as exc:
            self._json(500, {"ok": False, "error": str(exc)})


def main() -> int:
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"Gastro Print-Agent auf http://{BIND}:{PORT}", flush=True)
    print(f"Standarddrucker: {_default_printer() or '(keiner)'}", flush=True)
    print("Drucker:", ", ".join(_list_printers()) or "(keine)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStop.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
