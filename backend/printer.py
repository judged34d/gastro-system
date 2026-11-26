"""Stations-Orderbons (ESC/POS, 80mm) – Druck am Host, nicht im Browser."""
from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import threading
from pathlib import Path

log = logging.getLogger("gastro.printer")

CREATE_NO_WINDOW = 0x08000000
SETTINGS_KEY = "station_printers"
# 80mm @ Font A: ~48 Zeichen normal, ~24 bei doppelter Breite
PAPER_CHARS_80 = 42
PAPER_CHARS_DOUBLE = 21
# Thermodrucker typ. 203 dpi → ~576 px; etwas schmaler = sicherer Rand
LOGO_MAX_WIDTH = 384
LOGO_MAX_HEIGHT = 200
# A795: Bild-Logo (GS v 0) erzeugt oft Muell → standardmaessig aus
TICKET_LOGO_ENABLED = os.environ.get("GASTRO_TICKET_LOGO", "0").strip() in (
    "1",
    "true",
    "yes",
)
# Text-Kopf als TrueType-Raster; A795 oft Muell → default aus (GASTRO_TICKET_TTF=1 zum Test)
TICKET_TTF_HEADER = os.environ.get("GASTRO_TICKET_TTF", "0").strip() in (
    "1",
    "true",
    "yes",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _root_data_dir() -> Path:
    env = os.environ.get("GASTRO_DB_PATH")
    if env:
        return Path(env).resolve().parent
    return Path(__file__).resolve().parent.parent / "data"


def load_printer_config(conn) -> dict:
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?",
        (SETTINGS_KEY,),
    ).fetchone()
    if not row or not row["value"]:
        return {"autoprint": False, "stations": {}}
    try:
        data = json.loads(row["value"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"autoprint": False, "stations": {}}
    if not isinstance(data, dict):
        return {"autoprint": False, "stations": {}}
    stations = data.get("stations")
    if not isinstance(stations, dict):
        stations = {}
    return {
        "autoprint": bool(data.get("autoprint")),
        "stations": stations,
    }


def is_ticket_autoprint_enabled(conn) -> bool:
    return bool(load_printer_config(conn).get("autoprint"))


def save_printer_config(conn, data: dict) -> None:
    stations = {}
    raw = (data or {}).get("stations") or {}
    if isinstance(raw, dict):
        for sid, cfg in raw.items():
            key = str(sid).strip()
            if not key or not isinstance(cfg, dict):
                continue
            conn_type = str(cfg.get("connection") or "cups").strip().lower()
            if conn_type in ("ipp", "cups/ipp", "cups_ipp"):
                conn_type = "cups"
            if conn_type in ("station_agent", "local", "terminal", "agent"):
                # Alias: frueher Agent – jetzt Browser-Druck am Terminal
                if conn_type != "browser":
                    # agent mit URL bleibt fuer Spezialfaelle
                    if not str(cfg.get("agent_url") or "").strip():
                        conn_type = "browser"
                    else:
                        conn_type = "agent"
            default_port = 631 if conn_type == "cups" else 9100
            stations[key] = {
                "enabled": bool(cfg.get("enabled")),
                "connection": conn_type,
                "host": str(cfg.get("host") or "").strip(),
                "port": int(cfg.get("port") or default_port),
                "windows_name": str(cfg.get("windows_name") or "").strip(),
                "queue_name": str(cfg.get("queue_name") or "").strip(),
                "cups_user": str(cfg.get("cups_user") or "").strip(),
                "cups_password": str(cfg.get("cups_password") or ""),
                "agent_url": str(cfg.get("agent_url") or "").strip(),
                "copies": max(1, min(3, int(cfg.get("copies") or 1))),
            }
    payload = json.dumps(
        {
            "autoprint": bool((data or {}).get("autoprint")),
            "stations": stations,
        },
        ensure_ascii=False,
    )
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (SETTINGS_KEY, payload),
    )


def station_printer_cfg(conn, station_id: int) -> dict | None:
    """Verbindung fuer Station, wenn Drucker fuer diese Station aktiviert ist."""
    cfg = load_printer_config(conn)
    entry = cfg["stations"].get(str(station_id))
    if not entry or not entry.get("enabled"):
        return None
    return entry


def resolve_print_cfg(conn, station_id: int | None = None) -> tuple[dict | None, int]:
    """Drucker-Config: bevorzugte Station, sonst erste aktivierte."""
    if station_id:
        cfg = station_printer_cfg(conn, int(station_id))
        if cfg:
            return cfg, int(station_id)
    stations = load_printer_config(conn).get("stations") or {}
    for sid, entry in stations.items():
        if isinstance(entry, dict) and entry.get("enabled"):
            try:
                return entry, int(sid)
            except (TypeError, ValueError):
                continue
    return None, 0


def list_windows_printers() -> list[str]:
    if os.name != "nt":
        return []
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
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    names = []
    for line in (out.stdout or "").splitlines():
        name = line.strip()
        if name and name not in names:
            names.append(name)
    return names


def _encode(text: str) -> bytes:
    # ASCII-sicher fuer Raw-ESC/POS (Umlaute → Ersatz), keine Fancy-Zeichen.
    cleaned = (
        (text or "")
        .replace("—", "-")
        .replace("–", "-")
        .replace("…", "...")
        .replace("€", "EUR")
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("Ä", "Ae")
        .replace("Ö", "Oe")
        .replace("Ü", "Ue")
        .replace("ß", "ss")
    )
    return cleaned.encode("ascii", errors="replace")


def _nl(text: str = "") -> bytes:
    """A795: CRLF ist robuster als alleiniges LF."""
    return _encode(text) + b"\r\n"


def _line(char: str = "-", width: int = PAPER_CHARS_80) -> str:
    return char * width


def _size(n: int) -> bytes:
    """GS ! n – Bit0-3 Breite, Bit4-7 Hoehe."""
    return b"\x1d\x21" + bytes([n & 0xFF])


def _align(n: int) -> bytes:
    """ESC a n – 0 left, 1 center, 2 right."""
    return b"\x1b\x61" + bytes([n & 0xFF])


def _bold(on: bool) -> bytes:
    return b"\x1b\x45" + (b"\x01" if on else b"\x00")


def _escpos_init() -> bytes:
    # Nur Reset – A795 vertraegt sonst oft Muell bei Extra-Init
    return b"\x1b\x40"


def _escpos_cut() -> bytes:
    # Vorschub + Schnitt (ESC i); kein GS V
    return b"\r\n\r\n\r\n\x1b\x69"


def _ticket_logo_path() -> Path | None:
    root = _project_root()
    for rel in (
        "frontend/ticket_logo.png",  # Bajazz-Markenlogo fuer Bondruck
        "frontend/logo_clean.png",
        "frontend/ticket_logo.svg",
        "frontend/logo.png",
        "data/ticket_logo.png",
        "data/ticket_logo.svg",
    ):
        p = root / rel
        if p.is_file():
            return p
    return None


def _ticket_font_path(*, bold: bool = True) -> Path | None:
    """Schriftdatei fuer Bondruck-Kopf (Windows-Fonts bevorzugt)."""
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    candidates = (
        [
            windir / "georgiab.ttf",  # Georgia Bold – klar, etwas charaktervoll
            windir / "seguisb.ttf",  # Segoe UI Semibold
            windir / "segoeuib.ttf",
            windir / "arialbd.ttf",
            windir / "tahomabd.ttf",
            windir / "calibrib.ttf",
        ]
        if bold
        else [
            windir / "georgia.ttf",
            windir / "segoeui.ttf",
            windir / "arial.ttf",
            windir / "tahoma.ttf",
            windir / "calibri.ttf",
        ]
    )
    for p in candidates:
        if p.is_file():
            return p
    return None


def _image_to_escpos_raster(bw) -> bytes:
    """Pillow mode-1 Bild (0=schwarz) → GS v 0 Raster."""
    width, height = bw.size
    width_bytes = (width + 7) // 8
    target_w = width_bytes * 8
    if target_w != width:
        from PIL import Image

        padded = Image.new("1", (target_w, height), 1)
        padded.paste(bw, (0, 0))
        bw = padded
        width = target_w

    pixels = bw.load()
    data = bytearray()
    for y in range(height):
        for bx in range(width_bytes):
            byte = 0
            for bit in range(8):
                x = bx * 8 + bit
                if pixels[x, y] == 0:
                    byte |= 0x80 >> bit
            data.append(byte)

    header = (
        b"\x1d\x76\x30\x00"
        + bytes([width_bytes & 0xFF, (width_bytes >> 8) & 0xFF])
        + bytes([height & 0xFF, (height >> 8) & 0xFF])
    )
    return bytes(header) + bytes(data)


def _fit_text_width(
    draw, text: str, font_path: Path, start_size: int, max_w: int, min_size: int = 16
):
    """TrueType-Font so waehlen, dass Text in max_w passt. Liefert (font, text, bbox)."""
    from PIL import ImageFont

    display = text
    font = ImageFont.truetype(str(font_path), start_size)
    bbox = draw.textbbox((0, 0), display, font=font)
    for sz in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(str(font_path), sz)
        bbox = draw.textbbox((0, 0), display, font=font)
        if bbox[2] - bbox[0] <= max_w:
            return font, display, bbox
    while len(display) > 8 and (bbox[2] - bbox[0]) > max_w:
        display = display[:-1]
        bbox = draw.textbbox((0, 0), display + "...", font=font)
    display = display + "..."
    bbox = draw.textbbox((0, 0), display, font=font)
    return font, display, bbox


def _raster_text_header(brand: str, event_name: str = "") -> bytes:
    """Marke + Event als TrueType-Text-Raster (lesbarer als Drucker-Font)."""
    if not TICKET_TTF_HEADER:
        return b""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return b""

    font_path = _ticket_font_path(bold=True)
    event_font_path = _ticket_font_path(bold=False) or font_path
    if not font_path:
        return b""

    try:
        brand = (brand or "Schwarze 11").strip()
        event_name = (event_name or "").strip()
        max_w = LOGO_MAX_WIDTH
        pad_x, pad_y = 8, 8
        gap = 12 if event_name else 0
        content_w = max_w - 2 * pad_x

        probe = Image.new("L", (max_w, 40), 255)
        draw = ImageDraw.Draw(probe)
        brand_font, brand, brand_bb = _fit_text_width(
            draw, brand, font_path, 52, content_w, 28
        )
        brand_w = brand_bb[2] - brand_bb[0]
        brand_h = brand_bb[3] - brand_bb[1]

        event_font = event_bb = None
        event_w = event_h = 0
        if event_name and event_font_path:
            event_font, event_name, event_bb = _fit_text_width(
                draw, event_name, event_font_path, 28, content_w, 16
            )
            event_w = event_bb[2] - event_bb[0]
            event_h = event_bb[3] - event_bb[1]

        total_h = pad_y + brand_h + gap + event_h + pad_y + 4
        im = Image.new("L", (max_w, max(total_h, 1)), 255)
        draw = ImageDraw.Draw(im)
        draw.text(
            ((max_w - brand_w) // 2, pad_y - brand_bb[1]),
            brand,
            font=brand_font,
            fill=0,
        )
        if event_font and event_name and event_bb is not None:
            draw.text(
                (
                    (max_w - event_w) // 2,
                    pad_y + brand_h + gap - event_bb[1],
                ),
                event_name,
                font=event_font,
                fill=0,
            )
        draw.line((28, im.height - 2, max_w - 28, im.height - 2), fill=0, width=2)

        bw = im.point(lambda x: 0 if x < 128 else 255, mode="1")
        return _image_to_escpos_raster(bw)
    except Exception:
        log.exception("TTF-Kopf-Raster fehlgeschlagen")
        return b""


def _raster_logo_escpos() -> bytes:
    """Logo als ESC/POS-Raster (Thermodrucker kann kein SVG direkt)."""
    path = _ticket_logo_path()
    if not path:
        return b""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        log.warning("Pillow fehlt – Logo wird uebersprungen")
        return b""

    try:
        if path.suffix.lower() == ".svg":
            try:
                import io

                import cairosvg  # type: ignore

                png_bytes = cairosvg.svg2png(url=str(path))
                im = Image.open(io.BytesIO(png_bytes))
            except Exception:
                png = _project_root() / "frontend" / "logo_clean.png"
                if not png.is_file():
                    return b""
                im = Image.open(png)
        else:
            im = Image.open(path)

        im = im.convert("RGBA")
        # Schwarzer Bildhintergrund → transparent (sonst vollflaechig schwarz auf dem Bon)
        cleaned = []
        for r, g, b, a in im.getdata():
            if a < 8 or (r < 28 and g < 28 and b < 28):
                cleaned.append((255, 255, 255, 0))
            else:
                cleaned.append((r, g, b, a))
        im.putdata(cleaned)
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im).convert("RGB")
        im.thumbnail((LOGO_MAX_WIDTH, LOGO_MAX_HEIGHT), Image.Resampling.LANCZOS)
        gray = ImageOps.grayscale(im)
        bw = gray.point(lambda x: 0 if x < 200 else 255, mode="1")
        return _image_to_escpos_raster(bw)
    except Exception:
        log.exception("Logo-Raster fehlgeschlagen (%s)", path)
        return b""


def _wrap(text: str, width: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return [""]
    if len(text) <= width:
        return [text]
    lines: list[str] = []
    while text:
        if len(text) <= width:
            lines.append(text)
            break
        cut = text.rfind(" ", 0, width + 1)
        if cut <= 0:
            cut = width
        lines.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return lines


def build_station_ticket(
    *,
    station_name: str,
    waiter_name: str,
    table_name: str,
    order_number: int | str,
    created_at: str,
    items: list[dict],
    event_name: str = "",
) -> bytes:
    """ESC/POS-Laufzettel 80mm – Kopf mit Event, grosse Artikelzeilen."""
    out = bytearray()
    out.extend(_escpos_init())

    # Optional Bild-Logo – oft Muell auf A795, daher default aus
    if TICKET_LOGO_ENABLED:
        logo = _raster_logo_escpos()
        if logo:
            out.extend(_align(1))
            out.extend(logo)
            out.extend(b"\r\n")

    # Kopf: Marke + Event (ESC/POS – Reihenfolge "Schwarze 11")
    brand = "Schwarze 11"
    out.extend(_align(1))
    header = _raster_text_header(brand, event_name or "")
    if header:
        out.extend(header)
        out.extend(b"\r\n")
    else:
        out.extend(_size(0x11))
        out.extend(_bold(True))
        out.extend(_nl(brand))
        out.extend(_bold(False))
        out.extend(_size(0x00))
        if event_name:
            out.extend(_size(0x01))
            for part in _wrap(str(event_name), PAPER_CHARS_DOUBLE):
                out.extend(_nl(part))
            out.extend(_size(0x00))
        out.extend(_nl(_line("=")))

    out.extend(_align(1))
    out.extend(_size(0x01))  # nur doppelte Breite (stabiler als 0x11 überall)
    for part in _wrap((station_name or "STATION").upper(), PAPER_CHARS_DOUBLE):
        out.extend(_nl(part))
    out.extend(_size(0x00))
    out.extend(_nl(_line("-")))

    # Bedienung sehr gross
    out.extend(_align(1))
    out.extend(_size(0x11))
    out.extend(_bold(True))
    for part in _wrap((waiter_name or "-").upper(), PAPER_CHARS_DOUBLE):
        out.extend(_nl(part))
    out.extend(_bold(False))
    out.extend(_size(0x00))
    out.extend(_nl(_line("-")))

    # Tisch gross
    out.extend(_align(0))
    out.extend(_size(0x11))
    out.extend(_bold(True))
    for part in _wrap(f"TISCH {table_name or '-'}", PAPER_CHARS_DOUBLE):
        out.extend(_nl(part))
    out.extend(_bold(False))
    out.extend(_size(0x00))

    out.extend(_size(0x10))  # doppelte Hoehe
    out.extend(_nl(f"Order #{order_number}"))
    if created_at:
        out.extend(_nl(f"Zeit  {created_at}"))
    out.extend(_size(0x00))
    out.extend(_nl(_line("=")))

    for item in items:
        qty = int(item.get("quantity") or item.get("quantity_open") or 0)
        name = str(item.get("name") or "?")
        if qty <= 0:
            continue
        # Stückzahl und Artikel gleich: doppelte Hoehe (wie Artikel zuvor)
        out.extend(_size(0x10))
        out.extend(_bold(True))
        out.extend(_nl(f"{qty}x"))
        out.extend(_bold(False))
        for part in _wrap(name, PAPER_CHARS_80):
            out.extend(_nl(part))
        out.extend(_size(0x00))
        out.extend(_nl(""))

    out.extend(_nl(_line("=")))
    out.extend(_align(1))
    out.extend(_nl("Laufzettel - kein Kassenbon"))
    out.extend(_align(0))
    out.extend(_escpos_cut())
    return bytes(out)


def build_test_ticket(station_name: str) -> bytes:
    return build_station_ticket(
        station_name=station_name or "TEST",
        waiter_name="TEST BEDIENUNG",
        table_name="Tisch 0",
        order_number="0",
        created_at="--:--",
        event_name="Test-Event",
        items=[{"quantity": 1, "name": "Testdruck OK"}],
    )


def _euro_ascii(value: float) -> str:
    return ("%.2f" % float(value or 0)).replace(".", ",") + " EUR"


def build_tab_extract_ticket(
    *,
    tab_name: str,
    items: list[dict],
    total: float,
    event_name: str = "",
) -> bytes:
    """Kundlicher Deckel-Zwischenstand: Artikel, Stueckzahl, Gesamtsumme."""
    out = bytearray()
    out.extend(_escpos_init())
    out.extend(_align(1))
    out.extend(_size(0x11))
    out.extend(_bold(True))
    out.extend(_nl("Schwarze 11"))
    out.extend(_bold(False))
    out.extend(_size(0x00))
    if event_name:
        out.extend(_size(0x01))
        for part in _wrap(str(event_name), PAPER_CHARS_DOUBLE):
            out.extend(_nl(part))
        out.extend(_size(0x00))
    out.extend(_nl(_line("=")))
    out.extend(_size(0x01))
    out.extend(_nl("DECKEL"))
    out.extend(_size(0x00))
    out.extend(_bold(True))
    for part in _wrap(tab_name or "-", PAPER_CHARS_80):
        out.extend(_nl(part))
    out.extend(_bold(False))
    out.extend(_nl("Zwischenstand"))
    out.extend(_nl(_line("-")))
    out.extend(_align(0))

    for item in items:
        qty = int(item.get("quantity") or item.get("quantity_open") or 0)
        name = str(item.get("name") or "?")
        if qty <= 0:
            continue
        out.extend(_size(0x10))
        out.extend(_bold(True))
        out.extend(_nl(f"{qty}x"))
        out.extend(_bold(False))
        for part in _wrap(name, PAPER_CHARS_80):
            out.extend(_nl(part))
        out.extend(_size(0x00))
        out.extend(_nl(""))

    out.extend(_nl(_line("=")))
    out.extend(_align(1))
    out.extend(_size(0x11))
    out.extend(_bold(True))
    out.extend(_nl("GESAMT"))
    out.extend(_nl(_euro_ascii(total)))
    out.extend(_bold(False))
    out.extend(_size(0x00))
    out.extend(_nl(_line("-")))
    out.extend(_nl("Kein Kassenbon"))
    out.extend(_align(0))
    out.extend(_escpos_cut())
    return bytes(out)


def print_tab_extract(
    conn,
    *,
    tab_id: int,
    station_id: int | None = None,
    event_id: int | None = None,
) -> dict:
    """Offene Deckel-Positionen als Zwischenstand drucken."""
    tab = conn.execute(
        """
        SELECT t.id, t.name, t.event_id, e.name AS event_name
        FROM tabs t
        LEFT JOIN events e ON e.id = t.event_id
        WHERE t.id = ?
          AND t.active = 1
        """,
        (tab_id,),
    ).fetchone()
    if not tab:
        return {"ok": False, "error": "tab not found"}
    if event_id is not None and int(tab["event_id"]) != int(event_id):
        return {"ok": False, "error": "tab not found"}

    rows = conn.execute(
        """
        SELECT
            COALESCE(oi.product_name, p.name, 'Unbekannt') AS item_name,
            COALESCE(te.unit_price, oi.unit_price, p.price, 0) AS unit_price,
            te.quantity AS quantity_total,
            COALESCE((
                SELECT SUM(tpi.quantity)
                FROM tab_payment_items tpi
                WHERE tpi.tab_entry_id = te.id
            ), 0) AS quantity_paid
        FROM tab_entries te
        LEFT JOIN order_items oi ON oi.id = te.order_item_id
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE te.tab_id = ?
        ORDER BY te.id ASC
        """,
        (tab_id,),
    ).fetchall()

    # Gleichnamige offene Positionen zusammenfassen
    merged: dict[str, dict] = {}
    for r in rows:
        qty_open = max(0, int(r["quantity_total"] or 0) - int(r["quantity_paid"] or 0))
        if qty_open <= 0:
            continue
        name = str(r["item_name"] or "?")
        unit = float(r["unit_price"] or 0)
        slot = merged.get(name)
        if not slot:
            merged[name] = {"name": name, "quantity": qty_open, "unit_price": unit}
        else:
            slot["quantity"] += qty_open

    items = list(merged.values())
    if not items:
        return {"ok": False, "error": "Deckel ist leer / nichts offen"}

    total = sum(float(i["unit_price"]) * int(i["quantity"]) for i in items)
    payload = build_tab_extract_ticket(
        tab_name=str(tab["name"] or f"#{tab_id}"),
        items=items,
        total=total,
        event_name=str(tab["event_name"] or ""),
    )

    cfg, used_station = resolve_print_cfg(conn, station_id)
    if not cfg:
        return {"ok": False, "error": "Kein Drucker konfiguriert"}

    conn_type = str(cfg.get("connection") or "").lower()
    if conn_type in ("browser", "client"):
        import base64

        return {
            "ok": True,
            "client_print": True,
            "print_mode": "browser",
            "escpos_b64": base64.b64encode(payload).decode("ascii"),
            "bytes": len(payload),
            "total": total,
        }

    try:
        target = send_to_printer(cfg, payload, station_id=used_station or 0)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "target": target,
        "bytes": len(payload),
        "total": total,
        "station_id": used_station,
    }


def _send_network(host: str, port: int, payload: bytes) -> None:
    if not host:
        raise RuntimeError("Keine Drucker-IP gesetzt")
    with socket.create_connection((host, int(port or 9100)), timeout=4.0) as sock:
        sock.sendall(payload)


def _send_windows(printer_name: str, payload: bytes) -> None:
    if os.name != "nt":
        raise RuntimeError("Windows-Drucker nur unter Windows")
    if not printer_name:
        raise RuntimeError("Kein Windows-Druckername gesetzt")
    try:
        import win32print  # type: ignore
    except ImportError:
        win32print = None

    if win32print is not None:
        h = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(h, 1, ("GastroOrderBon", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, payload)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        return

    # Fallback ohne pywin32: RAW ueber Winspool-ctypes
    import ctypes
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv")
    OpenPrinter = winspool.OpenPrinterW
    OpenPrinter.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.HANDLE), wintypes.LPVOID]
    OpenPrinter.restype = wintypes.BOOL
    ClosePrinter = winspool.ClosePrinter
    ClosePrinter.argtypes = [wintypes.HANDLE]
    ClosePrinter.restype = wintypes.BOOL
    StartDocPrinter = winspool.StartDocPrinterW
    StartDocPrinter.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID]
    StartDocPrinter.restype = wintypes.DWORD
    EndDocPrinter = winspool.EndDocPrinter
    EndDocPrinter.argtypes = [wintypes.HANDLE]
    EndDocPrinter.restype = wintypes.BOOL
    StartPagePrinter = winspool.StartPagePrinter
    StartPagePrinter.argtypes = [wintypes.HANDLE]
    StartPagePrinter.restype = wintypes.BOOL
    EndPagePrinter = winspool.EndPagePrinter
    EndPagePrinter.argtypes = [wintypes.HANDLE]
    EndPagePrinter.restype = wintypes.BOOL
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
    if not OpenPrinter(printer_name, ctypes.byref(handle), None):
        raise RuntimeError(f"Drucker nicht oeffnen: {printer_name}")
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


def _send_file(station_id: int, payload: bytes) -> Path:
    data = _root_data_dir()
    data.mkdir(parents=True, exist_ok=True)
    path = data / f"last_ticket_station_{station_id}.bin"
    path.write_bytes(payload)
    txt = data / f"last_ticket_station_{station_id}.txt"
    txt.write_text(payload.decode("ascii", errors="replace"), encoding="utf-8", errors="replace")
    return path


def _ipp_attr(tag: int, name: str, value: bytes) -> bytes:
    nb = name.encode("ascii")
    return bytes([tag]) + len(nb).to_bytes(2, "big") + nb + value


def _ipp_name_without_lang(text: str) -> bytes:
    # IPP nameWithoutLanguage = nur Laenge + Bytes (KEIN Sprach-Prefix)
    raw = text.encode("ascii", errors="replace")
    return len(raw).to_bytes(2, "big") + raw


def _build_ipp_print_job(
    printer_uri: str, payload: bytes, document_format: bytes
) -> bytes:
    """IPP 1.1 Print-Job mit Rohdaten."""
    msg = bytearray()
    msg += b"\x01\x01"  # version 1.1
    msg += b"\x00\x02"  # Print-Job
    msg += b"\x00\x00\x00\x01"  # request-id
    msg += b"\x01"  # operation-attributes-tag
    msg += _ipp_attr(
        0x47, "attributes-charset", len(b"utf-8").to_bytes(2, "big") + b"utf-8"
    )
    msg += _ipp_attr(
        0x48,
        "attributes-natural-language",
        len(b"en").to_bytes(2, "big") + b"en",
    )
    uri_b = printer_uri.encode("ascii")
    msg += _ipp_attr(0x45, "printer-uri", len(uri_b).to_bytes(2, "big") + uri_b)
    msg += _ipp_attr(0x42, "requesting-user-name", _ipp_name_without_lang("gastro"))
    msg += _ipp_attr(0x42, "job-name", _ipp_name_without_lang("gastro-ticket"))
    msg += _ipp_attr(
        0x49,
        "document-format",
        len(document_format).to_bytes(2, "big") + document_format,
    )
    msg += b"\x03"  # end-of-attributes
    msg += payload
    return bytes(msg)


def _ipp_status_code(resp: bytes) -> int | None:
    if len(resp) < 8:
        return None
    return int.from_bytes(resp[2:4], "big")


def _ipp_find_status_message(resp: bytes) -> str:
    needle = b"status-message"
    idx = resp.find(needle)
    if idx < 0 or idx + len(needle) + 2 > len(resp):
        return ""
    vl_off = idx + len(needle)
    vlen = int.from_bytes(resp[vl_off : vl_off + 2], "big")
    start = vl_off + 2
    end = start + vlen
    if vlen <= 0 or end > len(resp):
        return ""
    return resp[start:end].decode("utf-8", errors="replace").strip()


def _ipp_layout_ok(body: bytes, payload: bytes) -> bool:
    """Sanity: Payload folgt auf end-of-attributes; job-name value-length > 0."""
    if not payload or not body.endswith(payload):
        return False
    eoa = len(body) - len(payload) - 1
    if eoa < 0 or body[eoa] != 0x03:
        return False
    jn = b"\x42" + len(b"job-name").to_bytes(2, "big") + b"job-name"
    pos = body.find(jn)
    if pos < 0:
        return False
    vlen = int.from_bytes(body[pos + len(jn) : pos + len(jn) + 2], "big")
    return vlen > 0


def _send_cups_ipp(
    host: str,
    queue_name: str,
    payload: bytes,
    port: int = 631,
    *,
    username: str = "",
    password: str = "",
) -> str:
    """Stiller Rohdruck an freigegebenen CUPS-Drucker (Ubuntu Raw-Queue)."""
    import base64
    import urllib.error
    import urllib.parse
    import urllib.request

    host = (host or "").strip()
    queue_name = (queue_name or "").strip()
    if not host or not queue_name:
        raise RuntimeError("CUPS: Terminal-IP und Drucker-Warteschlangenname noetig")
    if not payload:
        raise RuntimeError("CUPS: leerer ESC/POS-Payload")

    port = int(port or 631)
    qpath = urllib.parse.quote(queue_name, safe="-_.~")
    printer_uri = f"ipp://{host}:{port}/printers/{qpath}"
    url = f"http://{host}:{port}/printers/{qpath}"
    user = (username or "").strip()
    auth_header = ""
    if user:
        token = base64.b64encode(f"{user}:{password or ''}".encode("utf-8")).decode("ascii")
        auth_header = f"Basic {token}"

    # cups-raw zuerst = CUPS Raw-Pfad ohne Filter; octet-stream Fallback
    # Nach Energiesparen: kurz retry (CUPS/Netz braucht oft 1–2s)
    import time

    formats = (b"application/vnd.cups-raw", b"application/octet-stream")
    last_err: Exception | None = None
    for attempt in range(3):
        for fmt in formats:
            body = _build_ipp_print_job(printer_uri, payload, fmt)
            if not _ipp_layout_ok(body, payload):
                raise RuntimeError("CUPS: interner IPP-Layout-Fehler (job-name/payload)")
            headers = {
                "Content-Type": "application/ipp",
                "Content-Length": str(len(body)),
            }
            if auth_header:
                headers["Authorization"] = auth_header
            req = urllib.request.Request(
                url,
                data=body,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=12.0) as resp:
                    raw = resp.read(2048)
                    if resp.status and int(resp.status) >= 400:
                        raise RuntimeError(f"CUPS HTTP {resp.status}")
                    status = _ipp_status_code(raw)
                    if status is not None and status >= 0x0400:
                        msg = _ipp_find_status_message(raw)
                        detail = f" – {msg}" if msg else ""
                        if status == 0x0403:
                            hint = (
                                "CUPS sperrt Remote-Druck. Am Terminal einmal "
                                "dauerhaft ohne Auth: "
                                "bash ubuntu-cups-disable-auth.sh "
                                "(liegt unter Gastro frontend/ oder data/)"
                            )
                        else:
                            hint = "Queue muss Raw sein (Marke „Raw“)."
                        last_err = RuntimeError(
                            f"CUPS/IPP Status 0x{status:04x}{detail} "
                            f"(Format {fmt.decode('ascii')}). {hint}"
                        )
                        continue
                    return printer_uri
            except urllib.error.HTTPError as exc:
                err_body = exc.read(512)
                msg = _ipp_find_status_message(err_body) or err_body[:200].decode(
                    "utf-8", errors="replace"
                )
                last_err = RuntimeError(f"CUPS/IPP Fehler {exc.code}: {msg}")
            except urllib.error.URLError as exc:
                last_err = RuntimeError(
                    f"CUPS nicht erreichbar ({host}:{port}). "
                    f"Notebook wach / CUPS aktiv? ({exc})"
                )
            except Exception as exc:
                last_err = exc
        if attempt < 2:
            time.sleep(1.5)
    if last_err:
        raise last_err
    raise RuntimeError("CUPS: Druck fehlgeschlagen")


def _send_agent(agent_url: str, payload: bytes) -> str:
    import urllib.error
    import urllib.request

    url = (agent_url or "").strip().rstrip("/")
    if not url:
        raise RuntimeError(
            "Terminal-Agent: keine agent_url – Druck laeuft lokal im Browser "
            "(http://127.0.0.1:9109). Fuer Host-Autodruck IP des Terminals setzen."
        )
    if not url.endswith("/print"):
        url = url + "/print"
    body = json.dumps(
        {"escpos_b64": __import__("base64").b64encode(payload).decode("ascii")}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Print-Agent nicht erreichbar ({url}): {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or raw or "agent print failed")
    return str(data.get("target") or url)


def send_to_printer(cfg: dict, payload: bytes, *, station_id: int = 0) -> str:
    conn_type = str(cfg.get("connection") or "network").strip().lower()
    if conn_type in ("station_agent", "local", "terminal"):
        conn_type = "agent"
    elif conn_type in ("ipp", "cups/ipp", "cups_ipp"):
        conn_type = "cups"
    copies = max(1, min(3, int(cfg.get("copies") or 1)))
    last = "ok"
    for _ in range(copies):
        if conn_type == "network":
            _send_network(cfg.get("host") or "", int(cfg.get("port") or 9100), payload)
            last = f"network://{cfg.get('host')}:{cfg.get('port') or 9100}"
        elif conn_type == "cups":
            last = _send_cups_ipp(
                str(cfg.get("host") or ""),
                str(cfg.get("queue_name") or cfg.get("windows_name") or ""),
                payload,
                int(cfg.get("port") or 631),
                username=str(cfg.get("cups_user") or ""),
                password=str(cfg.get("cups_password") or ""),
            )
        elif conn_type == "windows":
            _send_windows(cfg.get("windows_name") or "", payload)
            last = f"windows://{cfg.get('windows_name')}"
        elif conn_type == "agent":
            last = _send_agent(str(cfg.get("agent_url") or ""), payload)
        elif conn_type == "file":
            path = _send_file(station_id, payload)
            last = f"file://{path}"
        elif conn_type in ("browser", "client"):
            raise RuntimeError(
                "Browser-Druck kann nicht still vom Host ausgefuehrt werden. "
                "Fuer Autodruck: Verbindung „CUPS/Ubuntu freigegeben“ waehlen."
            )
        else:
            raise RuntimeError(f"Unbekannte Verbindung: {conn_type}")
    return last


def fetch_station_ticket_data(conn, order_id: int, station_id: int) -> dict | None:
    order = conn.execute(
        """
        SELECT
            o.id,
            o.order_number,
            o.created_at,
            o.waiter_id,
            t.name AS table_name,
            u.name AS waiter_name,
            st.name AS station_name,
            e.name AS event_name
        FROM orders o
        LEFT JOIN tables t ON t.id = o.table_id
        LEFT JOIN users u ON u.id = o.waiter_id
        LEFT JOIN events e ON e.id = o.event_id
        LEFT JOIN users st ON st.id = ?
        WHERE o.id = ?
        """,
        (station_id, order_id),
    ).fetchone()
    if not order:
        return None

    items = conn.execute(
        """
        SELECT
            COALESCE(oi.product_name, p.name) AS name,
            oi.quantity_open AS quantity
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        JOIN station_categories sc
          ON sc.category_id = p.category_id
         AND sc.station_id = ?
         AND sc.event_id = p.event_id
        WHERE oi.order_id = ?
          AND oi.quantity_open > 0
        ORDER BY oi.id ASC
        """,
        (station_id, order_id),
    ).fetchall()
    item_list = [dict(i) for i in items if int(i["quantity"] or 0) > 0]
    if not item_list:
        return None

    created = str(order["created_at"] or "")
    # SQLite CURRENT_TIMESTAMP oft "YYYY-MM-DD HH:MM:SS"
    time_str = created[11:16] if len(created) >= 16 else created

    return {
        "station_name": order["station_name"] or f"Station {station_id}",
        "waiter_name": order["waiter_name"]
        or ("Gast/QR" if order["waiter_id"] is None else "—"),
        "table_name": order["table_name"] or "—",
        "order_number": order["order_number"] or order_id,
        "created_at": time_str,
        "event_name": order["event_name"] or "",
        "items": item_list,
    }


def build_station_ticket_payload(conn, order_id: int, station_id: int) -> dict | None:
    """Ticket-Daten + ESC/POS Base64 fuer Agent/Browser."""
    import base64

    data = fetch_station_ticket_data(conn, order_id, station_id)
    if not data:
        return None
    payload = build_station_ticket(**data)
    return {
        "ok": True,
        "order_id": order_id,
        "station_id": station_id,
        "ticket": data,
        "escpos_b64": base64.b64encode(payload).decode("ascii"),
    }


def print_station_order(conn, order_id: int, station_id: int) -> dict:
    cfg = station_printer_cfg(conn, station_id)
    if not cfg:
        return {"ok": False, "skipped": True, "reason": "printer disabled"}
    data = fetch_station_ticket_data(conn, order_id, station_id)
    if not data:
        return {"ok": False, "skipped": True, "reason": "no station items"}
    payload = build_station_ticket(**data)
    conn_type = str(cfg.get("connection") or "").lower()
    # Browser-Druck: nur Ticket liefern, Terminal-Browser druckt (kein Extra-Software)
    if conn_type in ("browser", "client"):
        return {
            "ok": False,
            "skipped": True,
            "reason": "client_browser",
            "client_print": True,
        }
    # Agent ohne URL → ebenfalls Client
    if conn_type in ("agent", "station_agent", "local", "terminal") and not (
        cfg.get("agent_url") or ""
    ).strip():
        return {
            "ok": False,
            "skipped": True,
            "reason": "client_browser",
            "client_print": True,
        }
    target = send_to_printer(cfg, payload, station_id=station_id)
    return {"ok": True, "target": target, "order_id": order_id, "station_id": station_id}


def print_station_order_async(order_id: int, station_ids: list[int]) -> None:
    """Nach Commit: nur wenn Autodruck aktiv – sonst manuell an der Theke."""
    ids = [int(s) for s in station_ids if s is not None]
    if not ids:
        return

    def _run() -> None:
        try:
            from db import get_db_connection

            conn = get_db_connection()
            try:
                if not is_ticket_autoprint_enabled(conn):
                    log.info("autoprint off – skip order=%s", order_id)
                    return
                for sid in ids:
                    try:
                        result = print_station_order(conn, order_id, sid)
                        if result.get("ok"):
                            log.info(
                                "ticket printed order=%s station=%s -> %s",
                                order_id,
                                sid,
                                result.get("target"),
                            )
                        elif not result.get("skipped"):
                            log.warning(
                                "ticket fail order=%s station=%s: %s",
                                order_id,
                                sid,
                                result,
                            )
                    except Exception as exc:
                        log.exception(
                            "ticket exception order=%s station=%s: %s",
                            order_id,
                            sid,
                            exc,
                        )
            finally:
                conn.close()
        except Exception as exc:
            log.exception("ticket worker failed: %s", exc)

    threading.Thread(target=_run, daemon=True, name=f"print-order-{order_id}").start()
