from flask import Blueprint, jsonify
from db import get_db_connection, get_active_event_id

products_bp = Blueprint('products', __name__)

@products_bp.route("/products")
def get_products():
    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    rows = conn.execute("""
        SELECT 
            p.id,
            p.name,
            p.price,
            p.category_id,
            c.name as category_name
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.active = 1
          AND p.event_id = ?
        ORDER BY p.name ASC
    """, (event_id,)).fetchall()

    conn.close()

    return jsonify([dict(r) for r in rows])
