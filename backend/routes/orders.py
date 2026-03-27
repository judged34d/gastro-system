# ============================================================
# [1000] IMPORTS
# ============================================================
from flask import Blueprint, request, jsonify
from db import get_db_connection

orders_bp = Blueprint('orders', __name__)

# ============================================================
# [1100] DISPLAY MIT OVERFLOW + DETAILDATEN FÜR KACHELN
# ============================================================
@orders_bp.route("/station/<int:station_id>/display")
def station_display(station_id):

    conn = get_db_connection()

    # ------------------------------------------------------------
    # [1110] ALLE RELEVANTEN ORDERS FÜR DIESE STATION
    # ------------------------------------------------------------
    orders = conn.execute("""
        SELECT
            o.id,
            o.order_number,
            oss.status,
            o.created_at
        FROM orders o
        JOIN order_station_status oss ON oss.order_id = o.id
        WHERE oss.station_id = ?
        ORDER BY o.created_at ASC
    """, (station_id,)).fetchall()

    total_orders = len(orders)

    # ------------------------------------------------------------
    # [1120] BISHERIGE DISPLAY-SLOTS LADEN
    # ------------------------------------------------------------
    slots = conn.execute("""
        SELECT *
        FROM station_display
        WHERE station_id = ?
        ORDER BY position ASC
    """, (station_id,)).fetchall()

    existing_ids = {s["order_id"] for s in slots}

    # ------------------------------------------------------------
    # [1130] NEUE ORDERS IN FREIE SLOTS EINORDNEN
    # ------------------------------------------------------------
    for o in orders:
        if o["id"] not in existing_ids:
            for pos in range(1, 16):
                taken = conn.execute("""
                    SELECT 1
                    FROM station_display
                    WHERE station_id = ? AND position = ?
                """, (station_id, pos)).fetchone()

                if not taken:
                    conn.execute("""
                        INSERT INTO station_display (station_id, order_id, position)
                        VALUES (?, ?, ?)
                    """, (station_id, o["id"], pos))
                    break

    conn.commit()

    # ------------------------------------------------------------
    # [1140] SLOTS NACH INSERTS NOCHMAL LADEN
    # ------------------------------------------------------------
    slots = conn.execute("""
        SELECT *
        FROM station_display
        WHERE station_id = ?
        ORDER BY position ASC
    """, (station_id,)).fetchall()

    display = []

    # ------------------------------------------------------------
    # [1150] ANZEIGEDATEN JE SLOT AUFBAUEN
    # ------------------------------------------------------------
    for s in slots[:15]:
        order_row = conn.execute("""
            SELECT
                o.id,
                o.order_number,
                o.table_id,
                o.waiter_id,
                oss.status,
                t.name AS table_name,
                u.name AS waiter_name
            FROM orders o
            JOIN order_station_status oss
                ON oss.order_id = o.id
            LEFT JOIN tables t
                ON t.id = o.table_id
            LEFT JOIN users u
                ON u.id = o.waiter_id
            WHERE o.id = ? AND oss.station_id = ?
        """, (s["order_id"], station_id)).fetchone()

        if not order_row:
            display.append(None)
            continue

        # --------------------------------------------------------
        # [1160] STATIONSRELEVANTE POSITIONEN DIESER ORDER
        # --------------------------------------------------------
        items = conn.execute("""
            SELECT
                p.name,
                p.price AS unit_price,
                oi.quantity_total,
                oi.quantity_open
            FROM order_items oi
            JOIN products p
                ON oi.product_id = p.id
            JOIN station_categories sc
                ON sc.category_id = p.category_id
            WHERE oi.order_id = ?
              AND sc.station_id = ?
            ORDER BY oi.id ASC
        """, (order_row["id"], station_id)).fetchall()

        item_list = []
        order_total = 0.0

        for i in items:
            line_total = float(i["quantity_open"]) * float(i["unit_price"])
            order_total += line_total

            item_list.append({
                "name": i["name"],
                "quantity_total": i["quantity_total"],
                "quantity_open": i["quantity_open"],
                "unit_price": float(i["unit_price"]),
                "line_total": line_total
            })

        display.append({
            "order_id": order_row["id"],
            "order_number": order_row["order_number"],
            "table_name": order_row["table_name"] if order_row["table_name"] else "Ohne Tisch",
            "waiter_name": order_row["waiter_name"] if order_row["waiter_name"] else "Unbekannt",
            "status": order_row["status"],
            "locked": s["locked"],
            "items": item_list,
            "order_total": order_total
        })

    conn.close()

    # ------------------------------------------------------------
    # [1170] AUF 15 SLOTS AUFFÜLLEN
    # ------------------------------------------------------------
    while len(display) < 15:
        display.append(None)

    waiting = max(0, total_orders - 15)

    return jsonify({
        "slots": display,
        "waiting": waiting
    })

# ============================================================
# [1200] STATUS UPDATE (FIXIERUNG HIER)
# ============================================================
@orders_bp.route("/station/<int:station_id>/orders/<int:order_id>/status", methods=["POST"])
def update_status(station_id, order_id):

    conn = get_db_connection()

    current = conn.execute("""
        SELECT status
        FROM order_station_status
        WHERE order_id = ? AND station_id = ?
    """, (order_id, station_id)).fetchone()

    if not current:
        conn.close()
        return jsonify({"error": "not found"}), 404

    if current["status"] == "new":
        new_status = "preparing"
    elif current["status"] == "preparing":
        new_status = "ready"
    else:
        new_status = "ready"

    conn.execute("""
        UPDATE order_station_status
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE order_id = ? AND station_id = ?
    """, (new_status, order_id, station_id))

    if new_status == "preparing":
        conn.execute("""
            UPDATE station_display
            SET locked = 1
            WHERE order_id = ? AND station_id = ?
        """, (order_id, station_id))

    conn.commit()
    conn.close()

    return jsonify({"status": new_status})

# ============================================================
# [1300] CREATE ORDER
# ============================================================
@orders_bp.route("/orders", methods=["POST"])
def create_order():
    data = request.json

    conn = get_db_connection()

    row = conn.execute("""
        SELECT MAX(order_number) AS max_nr
        FROM orders
    """).fetchone()

    next_number = (row["max_nr"] or 0) + 1

    cursor = conn.execute("""
        INSERT INTO orders (order_number, table_id, waiter_id, status)
        VALUES (?, ?, ?, 'new')
    """, (
        next_number,
        data.get("table_id"),
        data.get("waiter_id")
    ))

    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({"order_id": order_id})

# ============================================================
# [1400] ADD ITEM
# ============================================================
@orders_bp.route("/orders/<int:order_id>/items", methods=["POST"])
def add_item(order_id):
    data = request.json

    conn = get_db_connection()

    product = conn.execute("""
        SELECT category_id
        FROM products
        WHERE id = ?
    """, (data["product_id"],)).fetchone()

    if not product:
        conn.close()
        return jsonify({"error": "product not found"}), 404

    stations = conn.execute("""
        SELECT station_id
        FROM station_categories
        WHERE category_id = ?
    """, (product["category_id"],)).fetchall()

    existing = conn.execute("""
        SELECT *
        FROM order_items
        WHERE order_id = ?
          AND product_id = ?
          AND note = ?
    """, (
        order_id,
        data["product_id"],
        data.get("note", "")
    )).fetchone()

    qty = data.get("quantity", 1)

    if existing:
        conn.execute("""
            UPDATE order_items
            SET quantity_total = quantity_total + ?,
                quantity_open = quantity_open + ?
            WHERE id = ?
        """, (qty, qty, existing["id"]))
    else:
        conn.execute("""
            INSERT INTO order_items (
                order_id,
                product_id,
                note,
                quantity_total,
                quantity_open,
                quantity_paid
            )
            VALUES (?, ?, ?, ?, ?, 0)
        """, (
            order_id,
            data["product_id"],
            data.get("note", ""),
            qty,
            qty
        ))

    for s in stations:
        exists = conn.execute("""
            SELECT *
            FROM order_station_status
            WHERE order_id = ? AND station_id = ?
        """, (order_id, s["station_id"])).fetchone()

        if not exists:
            conn.execute("""
                INSERT INTO order_station_status (order_id, station_id, status)
                VALUES (?, ?, 'new')
            """, (order_id, s["station_id"]))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})
