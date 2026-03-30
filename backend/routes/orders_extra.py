from flask import Blueprint, jsonify
from db import get_db_connection, get_active_event_id

orders_extra_bp = Blueprint('orders_extra', __name__)

# ============================================================
# ORDERS FÜR TISCH (OFFEN)
# ============================================================
@orders_extra_bp.route("/table/<int:table_id>/orders")
def get_table_orders(table_id):

    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    orders = conn.execute("""
        SELECT id, order_number
        FROM orders
        WHERE table_id = ?
          AND event_id = ?
          AND status != 'paid'
        ORDER BY created_at ASC
    """, (table_id, event_id)).fetchall()

    result = []

    for o in orders:
        items = conn.execute("""
            SELECT
                oi.id,
                COALESCE(oi.product_name, p.name) AS name,
                COALESCE(oi.unit_price, p.price) AS price,
                oi.quantity_total,
                oi.quantity_open,
                oi.quantity_paid
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?
        """, (o["id"],)).fetchall()

        result.append({
            "order_id": o["id"],
            "order_number": o["order_number"],
            "items": [dict(i) for i in items]
        })

    conn.close()

    return jsonify(result)


@orders_extra_bp.route("/orders/status-board")
def orders_status_board():
    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    orders = conn.execute("""
        SELECT
            o.id,
            o.order_number,
            o.created_at,
            COALESCE(t.name, 'Theke') AS table_name,
            COALESCE(u.name, 'Unbekannt') AS waiter_name
        FROM orders o
        LEFT JOIN tables t ON t.id = o.table_id
        LEFT JOIN users u ON u.id = o.waiter_id
        WHERE o.event_id = ?
          AND o.status != 'paid'
        ORDER BY o.created_at ASC
    """, (event_id,)).fetchall()

    result = []
    for o in orders:
        items = conn.execute("""
            SELECT
                COALESCE(oi.product_name, p.name) AS name,
                COALESCE(oi.unit_price, p.price) AS price,
                oi.quantity_open
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?
              AND oi.quantity_open > 0
            ORDER BY oi.id ASC
        """, (o["id"],)).fetchall()
        if not items:
            continue

        station_stats = conn.execute("""
            SELECT
                COUNT(*) AS total_cnt,
                SUM(CASE WHEN status = 'ready' THEN 1 ELSE 0 END) AS ready_cnt
            FROM order_station_status
            WHERE order_id = ?
        """, (o["id"],)).fetchone()
        total_cnt = int(station_stats["total_cnt"] or 0)
        ready_cnt = int(station_stats["ready_cnt"] or 0)
        all_ready = total_cnt > 0 and ready_cnt == total_cnt

        total_open = sum(float(i["price"]) * int(i["quantity_open"]) for i in items)
        result.append({
            "order_id": o["id"],
            "order_number": o["order_number"],
            "table_name": o["table_name"],
            "waiter_name": o["waiter_name"],
            "created_at": o["created_at"],
            "all_ready": all_ready,
            "station_total": total_cnt,
            "station_ready": ready_cnt,
            "total_open": total_open,
            "items": [dict(i) for i in items],
        })

    conn.close()
    return jsonify(result)
