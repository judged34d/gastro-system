from flask import Blueprint, jsonify
from db import get_db_connection, get_active_event_id

tables_bp = Blueprint('tables', __name__)


@tables_bp.route("/public/table/<int:table_id>")
def public_table(table_id):
    """Öffentliche Tisch-Info für QR-Gastbestellung (nur aktives Event)."""
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    row = conn.execute("""
        SELECT id, name
        FROM tables
        WHERE id = ?
          AND event_id = ?
    """, (table_id, event_id)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify({"id": row["id"], "name": row["name"]})


@tables_bp.route("/waiter/<int:waiter_id>/tables")
def get_waiter_tables(waiter_id):

    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    rows = conn.execute("""
        SELECT t.id, t.name
        FROM tables t
        JOIN waiter_tables wt ON wt.table_id = t.id
        WHERE wt.waiter_id = ?
          AND t.event_id = ?
          AND wt.event_id = ?
    """, (waiter_id, event_id, event_id)).fetchall()

    conn.close()

    return jsonify([dict(r) for r in rows])


@tables_bp.route("/waiter/<int:waiter_id>/orders/open-count")
def waiter_open_orders_count(waiter_id):
    """Anzahl offener Bestellungen (mit offenen Positionen) auf den Tischen des Bedieners."""
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT o.id) AS cnt
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id AND oi.quantity_open > 0
        JOIN tables t ON t.id = o.table_id
        JOIN waiter_tables wt ON wt.table_id = t.id
        WHERE wt.waiter_id = ?
          AND wt.event_id = ?
          AND t.event_id = ?
          AND o.event_id = ?
          AND o.status != 'paid'
        """,
        (waiter_id, event_id, event_id, event_id),
    ).fetchone()
    conn.close()
    return jsonify({"count": int(row["cnt"] or 0) if row else 0})
