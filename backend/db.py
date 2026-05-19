# ============================================================
# [1000] DATABASE MODULE
# ============================================================
import os
import sqlite3

_DEFAULT_DB = (
    r"C:\Applikationen\Gastro-System\data\database.db"
    if os.name == "nt"
    else "/opt/gastro-system/data/database.db"
)
DB_PATH = os.environ.get("GASTRO_DB_PATH", _DEFAULT_DB)
# Bei Sperre durch gleichzeitige Schreibzugriffe: warten statt sofort „database is locked“ (Millisekunden).
SQLITE_BUSY_TIMEOUT_MS = int(os.environ.get("GASTRO_SQLITE_BUSY_MS", "8000"))


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Leichte Schema-Erweiterungen (idempotent)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "display_category_id" not in cols:
        conn.execute(
            "ALTER TABLE products ADD COLUMN display_category_id INTEGER"
        )
        conn.commit()

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "vat_rate" not in cols:
        conn.execute(
            "ALTER TABLE products ADD COLUMN vat_rate INTEGER NOT NULL DEFAULT 19"
        )
        conn.commit()

    cols_oi = {r["name"] for r in conn.execute("PRAGMA table_info(order_items)").fetchall()}
    if "vat_rate" not in cols_oi:
        conn.execute("ALTER TABLE order_items ADD COLUMN vat_rate INTEGER")
        conn.commit()

    cols_users = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "opening_cash" not in cols_users:
        conn.execute("ALTER TABLE users ADD COLUMN opening_cash REAL NOT NULL DEFAULT 0")
        conn.commit()
    cols_users = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "closing_cash" not in cols_users:
        conn.execute("ALTER TABLE users ADD COLUMN closing_cash REAL")
        conn.commit()

    # Stornojournal fuer nachvollziehbare Korrekturen inkl. Grund.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS order_item_cancellations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            order_item_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price REAL NOT NULL DEFAULT 0,
            amount REAL NOT NULL DEFAULT 0,
            created_by_role TEXT NOT NULL,
            created_by_user_id INTEGER,
            created_by_station_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_item_cancellations_event ON order_item_cancellations(event_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_item_cancellations_order ON order_item_cancellations(order_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('beta_cash_calculator', '0')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('single_terminal_mode', '0')"
    )

    cols_prod = {r["name"] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "icon_type" not in cols_prod:
        conn.execute(
            "ALTER TABLE products ADD COLUMN icon_type TEXT NOT NULL DEFAULT 'none'"
        )
        conn.commit()
    cols_prod = {r["name"] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "icon_ref" not in cols_prod:
        conn.execute("ALTER TABLE products ADD COLUMN icon_ref TEXT")
        conn.commit()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_icons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filename TEXT NOT NULL UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _configure_sqlite_connection(conn: sqlite3.Connection) -> None:
    """
    WAL: bessere Parallelitaet (Leser + Schreiber). Erzeugt neben der .db-Datei u. U. -wal und -shm.
    busy_timeout: kurze Warteschlange statt hartem Fehler bei Lock-Konkurrenz.
    """
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")

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

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    _configure_sqlite_connection(conn)
    _apply_migrations(conn)
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
