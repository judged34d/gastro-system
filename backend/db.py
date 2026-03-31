# ============================================================
# [1000] DATABASE MODULE
# ============================================================
import os
import sqlite3

DB_PATH = os.environ.get("GASTRO_DB_PATH", "/opt/gastro-system/data/database.db")

def get_active_event_id(conn):
    row = conn.execute("""
        SELECT id
        FROM events
        WHERE status = 'active'
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()
    if row:
        return row["id"]

    # Ensure there is always an active event, so the system remains operable
    # even after closing an event.
    cursor = conn.execute("""
        INSERT INTO events (name, status)
        VALUES ('Neues Event', 'active')
    """)
    conn.commit()
    return cursor.lastrowid

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def purge_orders_for_event(conn, event_id: int) -> int:
    """
    Loescht alle Orders des Events inkl. Zahlungen, Station-Slots und Theken-Display.
    Verhindert haengende Kacheln: station_display wird fuer alle Stationen des Events geleert.
    Gibt die Anzahl geloeschter Orders zurueck (vor dem DELETE).
    """
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM orders WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    n = int(row["c"])

    conn.execute("PRAGMA foreign_keys = ON")

    conn.execute(
        """
        DELETE FROM tab_payment_items WHERE tab_entry_id IN (
            SELECT id FROM tab_entries WHERE order_id IN (
                SELECT id FROM orders WHERE event_id = ?
            )
        )
        """,
        (event_id,),
    )
    conn.execute(
        """
        DELETE FROM tab_entries WHERE order_id IN (
            SELECT id FROM orders WHERE event_id = ?
        )
        """,
        (event_id,),
    )
    conn.execute(
        """
        DELETE FROM payment_items WHERE payment_id IN (
            SELECT id FROM payments WHERE order_id IN (
                SELECT id FROM orders WHERE event_id = ?
            )
        )
        """,
        (event_id,),
    )
    conn.execute(
        """
        DELETE FROM payments WHERE order_id IN (
            SELECT id FROM orders WHERE event_id = ?
        )
        """,
        (event_id,),
    )
    conn.execute(
        """
        DELETE FROM station_display WHERE order_id IN (
            SELECT id FROM orders WHERE event_id = ?
        )
        """,
        (event_id,),
    )
    conn.execute(
        """
        DELETE FROM station_display WHERE station_id IN (
            SELECT id FROM users WHERE event_id = ? AND role = 'station'
        )
        """,
        (event_id,),
    )
    conn.execute(
        """
        DELETE FROM order_station_status WHERE order_id IN (
            SELECT id FROM orders WHERE event_id = ?
        )
        """,
        (event_id,),
    )
    conn.execute(
        """
        DELETE FROM order_items WHERE order_id IN (
            SELECT id FROM orders WHERE event_id = ?
        )
        """,
        (event_id,),
    )
    conn.execute("DELETE FROM orders WHERE event_id = ?", (event_id,))
    conn.commit()
    return n


def purge_all_orders_global(conn) -> int:
    """Alle Orders aller Events inkl. Theken-Display-Zeilen (komplett leeren)."""
    row = conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()
    n = int(row["c"])
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        DELETE FROM tab_payment_items WHERE tab_entry_id IN (
            SELECT id FROM tab_entries WHERE order_id IN (SELECT id FROM orders)
        )
        """
    )
    conn.execute(
        "DELETE FROM tab_entries WHERE order_id IN (SELECT id FROM orders)"
    )
    conn.execute(
        """
        DELETE FROM payment_items WHERE payment_id IN (
            SELECT id FROM payments WHERE order_id IN (SELECT id FROM orders)
        )
        """
    )
    conn.execute(
        "DELETE FROM payments WHERE order_id IN (SELECT id FROM orders)"
    )
    conn.execute("DELETE FROM station_display")
    conn.execute(
        "DELETE FROM order_station_status WHERE order_id IN (SELECT id FROM orders)"
    )
    conn.execute(
        "DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders)"
    )
    conn.execute("DELETE FROM orders")
    conn.commit()
    return n


def purge_database_for_live(conn, new_event_name: str) -> tuple[int, int]:
    """
    Orders + alle Stammdaten (Kategorien, Artikel, Tische, User, Tabs) aller Events loeschen,
    dann ein neues aktives Event anlegen. Fuer ersten Live-Start nach Tests.
    """
    n_orders = purge_all_orders_global(conn)
    for sql in (
        "DELETE FROM tab_payment_items",
        "DELETE FROM tab_entries",
        "DELETE FROM tab_payments",
        "DELETE FROM tabs",
        "DELETE FROM waiter_tables",
        "DELETE FROM station_categories",
        "DELETE FROM products",
        "DELETE FROM categories",
        "DELETE FROM tables",
        "DELETE FROM users",
        "DELETE FROM events",
    ):
        conn.execute(sql)
    cur = conn.execute(
        "INSERT INTO events (name, status) VALUES (?, 'active')",
        (new_event_name.strip() or "Live",),
    )
    new_id = cur.lastrowid
    conn.commit()
    return n_orders, new_id


def sql_tab_open_balance(tab_alias="t"):
    """
    SQLite scalar expression: open monetary balance for one tab row (alias e.g. t).
    Uses unpaid quantities × unit price per tab_entry (same logic as /tabs/<id>/items).
    Never negative (keine „Gutschrift“-Anzeige bei Dateninkonsistenzen).
    """
    inner = f"""COALESCE((
        SELECT SUM(
            MAX(0, te.quantity - COALESCE((
                SELECT SUM(tpi.quantity) FROM tab_payment_items tpi WHERE tpi.tab_entry_id = te.id
            ), 0)) * MAX(0, COALESCE(te.unit_price, oi.unit_price, p.price, 0))
        )
        FROM tab_entries te
        LEFT JOIN order_items oi ON oi.id = te.order_item_id
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE te.tab_id = {tab_alias}.id
    ), 0)"""
    return f"MAX(0, {inner})"
