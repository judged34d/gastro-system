"""Demo-Event: Anlegen, Befüllen und Zurücksetzen."""

from __future__ import annotations

from db import purge_orders_for_event, purge_tabs_for_event

DEMO_EVENT_NAME = "Demo – Schützenfest"

_DEMO_CATEGORIES = ("Getränke", "Speisen")

_DEMO_PRODUCTS = (
    ("Bier 0,5 l", 3.50, "Getränke", 19),
    ("Radler 0,5 l", 3.50, "Getränke", 19),
    ("Cola 0,5 l", 3.00, "Getränke", 19),
    ("Wasser 0,5 l", 2.50, "Getränke", 19),
    ("Bratwurst", 4.50, "Speisen", 7),
    ("Pommes", 3.50, "Speisen", 7),
    ("Schnitzel", 12.00, "Speisen", 7),
)

_DEMO_TABLES = tuple(f"Tisch {i}" for i in range(1, 7))

_DEMO_USERS = (
    ("Demo Bedienung", "1111", "waiter", 100.0),
    ("Demo Bedienung 2", "3333", "waiter", 50.0),
    ("Demo Theke", "2222", "station", 250.0),
)


def seed_demo_event_data(conn, event_id: int) -> None:
    """Stammdaten für ein Demo-Event anlegen (idempotent nur bei leerem Event)."""
    existing = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if int(existing["c"]) > 0:
        return

    cat_map: dict[str, int] = {}
    for name in _DEMO_CATEGORIES:
        cur = conn.execute(
            "INSERT INTO categories (event_id, name) VALUES (?, ?)",
            (event_id, name),
        )
        cat_map[name] = int(cur.lastrowid)

    for idx, (name, price, cat_name, vat) in enumerate(_DEMO_PRODUCTS, start=1):
        cat_id = cat_map[cat_name]
        conn.execute(
            """
            INSERT INTO products (
                event_id, name, price, category_id, display_category_id,
                active, vat_rate, icon_type, sort_order
            )
            VALUES (?, ?, ?, ?, ?, 1, ?, 'none', ?)
            """,
            (event_id, name, price, cat_id, cat_id, vat, idx),
        )

    table_map: dict[str, int] = {}
    for name in _DEMO_TABLES:
        cur = conn.execute(
            "INSERT INTO tables (event_id, name, active) VALUES (?, ?, 1)",
            (event_id, name),
        )
        table_map[name] = int(cur.lastrowid)

    user_map: dict[str, int] = {}
    for name, pin, role, opening_cash in _DEMO_USERS:
        cur = conn.execute(
            """
            INSERT INTO users (event_id, name, pin, role, active, opening_cash, closing_cash)
            VALUES (?, ?, ?, ?, 1, ?, NULL)
            """,
            (event_id, name, pin, role, opening_cash),
        )
        user_map[name] = int(cur.lastrowid)

    waiter_ids = [user_map["Demo Bedienung"], user_map["Demo Bedienung 2"]]
    table_ids = list(table_map.values())
    for i, table_id in enumerate(table_ids):
        waiter_id = waiter_ids[i % len(waiter_ids)]
        conn.execute(
            """
            INSERT INTO waiter_tables (event_id, waiter_id, table_id)
            VALUES (?, ?, ?)
            """,
            (event_id, waiter_id, table_id),
        )

    station_id = user_map["Demo Theke"]
    for cat_id in cat_map.values():
        conn.execute(
            """
            INSERT INTO station_categories (event_id, station_id, category_id)
            VALUES (?, ?, ?)
            """,
            (event_id, station_id, cat_id),
        )


def ensure_demo_event(conn) -> int:
    """Demo-Event vorhanden und befüllt halten. Gibt die Demo-Event-ID zurück."""
    row = conn.execute(
        "SELECT id FROM events WHERE is_demo = 1 ORDER BY id ASC LIMIT 1",
    ).fetchone()
    if row:
        event_id = int(row["id"])
        seed_demo_event_data(conn, event_id)
        conn.commit()
        return event_id

    cur = conn.execute(
        """
        INSERT INTO events (name, status, is_demo)
        VALUES (?, 'closed', 1)
        """,
        (DEMO_EVENT_NAME,),
    )
    event_id = int(cur.lastrowid)
    seed_demo_event_data(conn, event_id)
    conn.commit()
    return event_id


def get_demo_event(conn) -> dict | None:
    row = conn.execute(
        """
        SELECT id, name, status, COALESCE(is_demo, 0) AS is_demo
        FROM events
        WHERE is_demo = 1
        ORDER BY id ASC
        LIMIT 1
        """,
    ).fetchone()
    return dict(row) if row else None


def reset_demo_event(conn, event_id: int | None = None) -> dict | None:
    """Buchungen/Deckel löschen und Demo-Stammdaten neu aufsetzen."""
    if event_id is None:
        demo = get_demo_event(conn)
        if not demo:
            event_id = ensure_demo_event(conn)
        else:
            event_id = int(demo["id"])
    else:
        demo = conn.execute(
            "SELECT id, name, is_demo FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if not demo or not int(demo["is_demo"] or 0):
            return None

    purge_orders_for_event(conn, int(event_id))
    purge_tabs_for_event(conn, int(event_id))

    conn.execute(
        "DELETE FROM waiter_tables WHERE event_id = ?",
        (event_id,),
    )
    conn.execute(
        "DELETE FROM station_categories WHERE event_id = ?",
        (event_id,),
    )
    conn.execute("DELETE FROM products WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM categories WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM tables WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM users WHERE event_id = ?", (event_id,))

    seed_demo_event_data(conn, int(event_id))
    conn.execute(
        """
        UPDATE events
        SET ends_at = NULL
        WHERE id = ? AND status = 'active'
        """,
        (event_id,),
    )
    conn.commit()

    ev = conn.execute(
        "SELECT id, name, status FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()
    return {
        "event_id": int(ev["id"]),
        "event_name": ev["name"],
        "status": ev["status"],
        "reset": True,
    }
