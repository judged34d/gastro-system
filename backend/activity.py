"""Live-Aktivitaetslog fuer Control Panel und Monitoring (Push via SSE)."""

from __future__ import annotations

import json
import threading
import time
from collections import deque

_bus_lock = threading.Lock()
_bus_cond = threading.Condition(_bus_lock)
_recent: deque[dict] = deque(maxlen=300)
_latest_id = 0


def ensure_activity_log_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            order_id INTEGER,
            order_number INTEGER,
            amount REAL,
            actor TEXT,
            station_name TEXT,
            meta_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_log_id ON activity_log(id DESC)"
    )


def _event_from_row(row) -> dict:
    d = dict(row)
    if d.get("amount") is not None:
        d["amount"] = float(d["amount"])
    return d


def publish_activity_event(event: dict) -> None:
    """Sofort an SSE-Listener pushen (kein Poll-Takt)."""
    global _latest_id
    with _bus_cond:
        _recent.append(event)
        _latest_id = max(_latest_id, int(event.get("id") or 0))
        _bus_cond.notify_all()


def wait_activity_events(since_id: int, timeout: float = 20.0) -> list[dict]:
    """Blockiert bis neue Events da sind oder Timeout (fuer SSE-Keepalive)."""
    since_id = max(0, int(since_id or 0))
    deadline = time.monotonic() + max(0.2, float(timeout))
    with _bus_cond:
        while True:
            fresh = [e for e in _recent if int(e.get("id") or 0) > since_id]
            if fresh:
                return fresh
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return []
            _bus_cond.wait(timeout=remaining)


def latest_activity_id() -> int:
    with _bus_lock:
        return int(_latest_id or 0)


def log_activity(
    conn,
    kind: str,
    message: str,
    *,
    order_id: int | None = None,
    order_number: int | None = None,
    amount: float | None = None,
    actor: str | None = None,
    station_name: str | None = None,
    meta: dict | None = None,
) -> None:
    ensure_activity_log_table(conn)
    cur = conn.execute(
        """
        INSERT INTO activity_log (
            kind, message, order_id, order_number, amount, actor, station_name, meta_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kind,
            message,
            order_id,
            order_number,
            amount,
            actor,
            station_name,
            json.dumps(meta, ensure_ascii=False) if meta else None,
        ),
    )
    event_id = int(cur.lastrowid)
    row = conn.execute(
        """
        SELECT id, kind, message, order_id, order_number, amount, actor,
               station_name, created_at
        FROM activity_log
        WHERE id = ?
        """,
        (event_id,),
    ).fetchone()
    if row:
        publish_activity_event(_event_from_row(row))


def fetch_activity(conn, since_id: int = 0, limit: int = 80) -> list[dict]:
    ensure_activity_log_table(conn)
    limit = max(1, min(int(limit or 80), 200))
    since_id = max(0, int(since_id or 0))
    if since_id > 0:
        rows = conn.execute(
            """
            SELECT id, kind, message, order_id, order_number, amount, actor,
                   station_name, created_at
            FROM activity_log
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (since_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, kind, message, order_id, order_number, amount, actor,
                   station_name, created_at
            FROM activity_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        rows = list(reversed(rows))
    return [_event_from_row(r) for r in rows]


def format_euro(v: float | None) -> str:
    if v is None:
        return "0,00 €"
    return f"{float(v):.2f}".replace(".", ",") + " €"


def order_open_amount(conn, order_id: int) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(
            oi.quantity_open * COALESCE(oi.unit_price, p.price, 0)
        ), 0) AS total
        FROM order_items oi
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        """,
        (order_id,),
    ).fetchone()
    return float(row["total"] or 0) if row else 0.0


def order_meta(conn, order_id: int) -> dict:
    row = conn.execute(
        """
        SELECT
            o.id,
            o.order_number,
            o.source,
            u.name AS waiter_name,
            st.name AS station_name,
            t.name AS table_name
        FROM orders o
        LEFT JOIN users u ON u.id = o.waiter_id
        LEFT JOIN users st ON st.id = o.source_station_id
        LEFT JOIN tables t ON t.id = o.table_id
        WHERE o.id = ?
        """,
        (order_id,),
    ).fetchone()
    return dict(row) if row else {}


def log_order_created(conn, order_id: int) -> None:
    meta = order_meta(conn, order_id)
    if not meta:
        return
    amount = order_open_amount(conn, order_id)
    onr = int(meta.get("order_number") or 0)
    source = meta.get("source") or "waiter"
    if source == "station":
        actor = meta.get("station_name") or "Theke"
        msg = (
            f"{actor} nimmt Bestellung #{onr} mit Wert von {format_euro(amount)} auf"
        )
    elif source == "guest_qr":
        actor = "Gast (QR)"
        table = meta.get("table_name") or "Tisch"
        msg = (
            f"{actor} an {table} nimmt Bestellung #{onr} "
            f"mit Wert von {format_euro(amount)} auf"
        )
    else:
        actor = meta.get("waiter_name") or "Bedienung"
        table = meta.get("table_name") or "Tisch"
        msg = (
            f"{actor} nimmt Bestellung #{onr} ({table}) "
            f"mit Wert von {format_euro(amount)} auf"
        )
    log_activity(
        conn,
        "order_created",
        msg,
        order_id=order_id,
        order_number=onr,
        amount=amount,
        actor=actor,
        station_name=meta.get("station_name"),
    )


def log_station_status(conn, order_id: int, station_id: int, status: str) -> None:
    meta = order_meta(conn, order_id)
    onr = int(meta.get("order_number") or 0) if meta else 0
    station = conn.execute(
        "SELECT name FROM users WHERE id = ?",
        (station_id,),
    ).fetchone()
    station_name = station["name"] if station else f"Theke {station_id}"
    if status == "preparing":
        msg = f"Bestellung #{onr} wird an {station_name} bearbeitet"
        kind = "order_preparing"
    elif status == "ready":
        msg = f"Bestellung #{onr} ist bereit ({station_name})"
        kind = "order_ready"
    else:
        msg = f"Bestellung #{onr}: Status {status} ({station_name})"
        kind = "order_status"
    log_activity(
        conn,
        kind,
        msg,
        order_id=order_id,
        order_number=onr or None,
        actor=station_name,
        station_name=station_name,
    )


def log_order_paid(conn, order_id: int, amount: float | None = None, how: str = "kassiert") -> None:
    meta = order_meta(conn, order_id)
    onr = int(meta.get("order_number") or 0) if meta else 0
    pay_amount = amount if amount is not None else order_open_amount(conn, order_id)
    msg = f"Bestellung #{onr} ist {how}"
    if pay_amount and how == "kassiert":
        msg = f"Bestellung #{onr} ist kassiert ({format_euro(pay_amount)})"
    log_activity(
        conn,
        "order_paid",
        msg,
        order_id=order_id,
        order_number=onr or None,
        amount=pay_amount,
        actor=meta.get("waiter_name") or meta.get("station_name"),
    )
