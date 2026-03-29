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
    # Keep paid orders out of station flow.
    orders = conn.execute("""
        SELECT
            o.id,
            o.order_number,
            oss.status,
            o.created_at
        FROM orders o
        JOIN order_station_status oss ON oss.order_id = o.id
        WHERE oss.station_id = ?
          AND o.status != 'paid'
        ORDER BY o.created_at ASC
    """, (station_id,)).fetchall()

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
              AND oi.quantity_open > 0
            ORDER BY oi.id ASC
        """, (order_row["id"], station_id)).fetchall()

        if len(items) == 0:
            # Remove stale slot so new orders can move up.
            conn.execute("""
                DELETE FROM station_display
                WHERE station_id = ? AND order_id = ?
            """, (station_id, s["order_id"]))
            continue

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

    # ------------------------------------------------------------
    # [1170] AUF 15 SLOTS AUFFÜLLEN
    # ------------------------------------------------------------
    while len(display) < 15:
        display.append(None)

    # Count only station-relevant orders that still have open items.
    open_station_orders = conn.execute("""
        SELECT COUNT(DISTINCT oi.order_id) AS cnt
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        JOIN station_categories sc ON sc.category_id = p.category_id
        JOIN orders o ON o.id = oi.order_id
        WHERE sc.station_id = ?
          AND oi.quantity_open > 0
          AND o.status != 'paid'
    """, (station_id,)).fetchone()["cnt"]

    waiting = max(0, open_station_orders - 15)

    conn.commit()
    conn.close()

    return jsonify({
        "slots": display[:15],
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

# ============================================================
# [1500] PAY ITEM
# ============================================================
@orders_bp.route("/orders/<int:order_id>/pay-item", methods=["POST"])
def pay_item(order_id):
    data = request.json
    order_item_id = data.get("order_item_id")
    quantity = data.get("quantity", 1)

    conn = get_db_connection()

    if order_item_id is None or quantity is None:
        conn.close()
        return jsonify({"error": "invalid quantity"}), 400

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        conn.close()
        return jsonify({"error": "invalid quantity"}), 400

    if quantity <= 0:
        conn.close()
        return jsonify({"error": "invalid quantity"}), 400

    item = conn.execute("""
        SELECT oi.*, p.price
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.id = ?
          AND oi.order_id = ?
    """, (order_item_id, order_id)).fetchone()

    if not item or item["quantity_open"] < quantity:
        conn.close()
        return jsonify({"error": "invalid"}), 400

    amount = item["price"] * quantity

    cursor = conn.execute("""
        INSERT INTO payments (order_id, amount)
        VALUES (?, ?)
    """, (order_id, amount))

    payment_id = cursor.lastrowid

    conn.execute("""
        INSERT INTO payment_items (payment_id, order_item_id, quantity)
        VALUES (?, ?, ?)
    """, (payment_id, order_item_id, quantity))

    conn.execute("""
        UPDATE order_items
        SET quantity_open = quantity_open - ?,
            quantity_paid = quantity_paid + ?
        WHERE id = ?
    """, (quantity, quantity, order_item_id))

    remaining = conn.execute("""
        SELECT SUM(quantity_open) AS open_sum
        FROM order_items
        WHERE order_id = ?
    """, (order_id,)).fetchone()

    if remaining["open_sum"] == 0:
        conn.execute("""
            UPDATE orders
            SET status = 'paid'
            WHERE id = ?
        """, (order_id,))

    conn.commit()
    conn.close()

    return jsonify({"paid_amount": amount})

# ============================================================
# [1600] ORDER TOTALS
# ============================================================
@orders_bp.route("/orders/<int:order_id>/totals")
def order_totals(order_id):
    conn = get_db_connection()

    rows = conn.execute("""
        SELECT oi.quantity_total, oi.quantity_open, p.price
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
    """, (order_id,)).fetchall()

    conn.close()

    total = 0
    open_amount = 0

    for r in rows:
        total += r["quantity_total"] * r["price"]
        open_amount += r["quantity_open"] * r["price"]

    paid = total - open_amount

    return jsonify({
        "total": total,
        "open": open_amount,
        "paid": paid
    })

# ============================================================
# [1700] GET ORDER
# ============================================================
@orders_bp.route("/orders/<int:order_id>")
def get_order(order_id):
    conn = get_db_connection()

    items = conn.execute("""
        SELECT oi.id, p.name, p.price,
               oi.quantity_total, oi.quantity_open, oi.quantity_paid
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
    """, (order_id,)).fetchall()

    conn.close()

    return jsonify([dict(i) for i in items])

# ============================================================
# [1800] GLOBAL STATUS (BEDIENUNG)
# ============================================================
@orders_bp.route("/orders/<int:order_id>/status")
def get_order_status(order_id):

    conn = get_db_connection()

    order = conn.execute("""
        SELECT status
        FROM orders
        WHERE id = ?
    """, (order_id,)).fetchone()

    if order and order["status"] == "paid":
        conn.close()
        return jsonify({"status": "Bezahlt"})

    rows = conn.execute("""
        SELECT status
        FROM order_station_status
        WHERE order_id = ?
    """, (order_id,)).fetchall()

    conn.close()

    statuses = [r["status"] for r in rows]

    if statuses and all(s == "ready" for s in statuses):
        return jsonify({"status": "Fertig"})

    if any(s == "preparing" for s in statuses):
        return jsonify({"status": "Zubereitung"})

    return jsonify({"status": "Neu"})
