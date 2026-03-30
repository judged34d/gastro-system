# ============================================================
# [1000] DATABASE MODULE
# ============================================================
import sqlite3

DB_PATH = "/opt/gastro-system/data/database.db"

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
