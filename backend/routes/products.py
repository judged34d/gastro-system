from flask import Blueprint, jsonify
from db import get_db_connection, get_active_event_id
from routes.icons import enrich_product_icon

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
            c.name AS category_name,
            COALESCE(p.sort_order, p.id) AS sort_order,
            COALESCE(dc.id, p.category_id) AS menu_category_id,
            COALESCE(dc.name, c.name) AS menu_category_name,
            COALESCE(p.icon_type, 'none') AS icon_type,
            p.icon_ref
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        LEFT JOIN categories dc ON dc.id = p.display_category_id
          AND dc.event_id = p.event_id
        WHERE p.active = 1
          AND p.event_id = ?
        ORDER BY menu_category_name ASC, sort_order ASC, p.name ASC
    """, (event_id,)).fetchall()

    out = [enrich_product_icon(conn, dict(r)) for r in rows]
    conn.close()

    resp = jsonify(out)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp
