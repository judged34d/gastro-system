from flask import Blueprint, jsonify
from db import get_db_connection

orders_extra_bp = Blueprint('orders_extra', __name__)

# ============================================================
# ORDERS FÜR TISCH (OFFEN)
# ============================================================
@orders_extra_bp.route("/table/<int:table_id>/orders")
def get_table_orders(table_id):

    conn = get_db_connection()

    orders = conn.execute("""
        SELECT id, order_number
        FROM orders
        WHERE table_id = ?
          AND status != 'paid'
        ORDER BY created_at ASC
    """, (table_id,)).fetchall()

    result = []

    for o in orders:
        items = conn.execute("""
            SELECT
                oi.id,
                p.name,
                p.price,
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
