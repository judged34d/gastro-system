from flask import Blueprint, request, jsonify
from db import get_db_connection, sql_tab_open_balance

orders_bp = Blueprint('orders', __name__)

def _get_active_event_id(conn):
    row = conn.execute("""
        SELECT id
        FROM events
        WHERE status = 'active'
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    if row:
        return row["id"]

    cursor = conn.execute("""
        INSERT INTO events (name, status)
        VALUES ('Default Event', 'active')
    """)
    return cursor.lastrowid


def _get_station_event_id(conn, station_id):
    row = conn.execute("""
        SELECT event_id
        FROM users
        WHERE id = ?
          AND role = 'station'
          AND active = 1
    """, (station_id,)).fetchone()
    return row["event_id"] if row else None


def _list_tabs_for_event(conn, event_id):
    bal = sql_tab_open_balance("t")
    rows = conn.execute(f"""
        SELECT
            t.id,
            t.name,
            {bal} AS balance,
            COALESCE((SELECT SUM(te.amount) FROM tab_entries te WHERE te.tab_id = t.id), 0) AS entries_amount,
            COALESCE((SELECT SUM(tp.amount) FROM tab_payments tp WHERE tp.tab_id = t.id), 0) AS payments_amount
        FROM tabs t
        WHERE t.event_id = ?
          AND t.active = 1
        ORDER BY t.name COLLATE NOCASE ASC
    """, (event_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["balance"] = max(0.0, float(d.get("balance") or 0))
        out.append(d)
    return out


def _order_status_payload(conn, order_id: int):
    """Gleiche Logik wie GET /orders/<id>/status (Bedienung + Viewer)."""
    order = conn.execute("""
        SELECT status
        FROM orders
        WHERE id = ?
    """, (order_id,)).fetchone()

    if order and order["status"] == "paid":
        return {"status": "Bezahlt", "status_key": "paid"}

    rows = conn.execute("""
        SELECT status
        FROM order_station_status
        WHERE order_id = ?
    """, (order_id,)).fetchall()

    statuses = [str(r["status"] or "").lower() for r in rows]
    total = len(statuses)
    ready = sum(1 for s in statuses if s == "ready")
    preparing = sum(1 for s in statuses if s == "preparing")
    new_cnt = sum(1 for s in statuses if s == "new")

    if total > 0 and ready == total:
        return {"status": "Fertig", "status_key": "ready"}

    if total > 0 and new_cnt == total:
        return {"status": "Offen", "status_key": "open"}

    if total > 0 and new_cnt > 0 and (preparing > 0 or ready > 0):
        return {"status": "Teilweise in Zubereitung", "status_key": "partial"}

    if total > 0 and new_cnt == 0 and ready < total:
        return {"status": "In Zubereitung", "status_key": "preparing"}

    return {"status": "Offen", "status_key": "open"}


# ============================================================
# [1100] DISPLAY MIT OVERFLOW + DETAILDATEN FÜR KACHELN
# ============================================================
@orders_bp.route("/station/<int:station_id>/display")
def station_display(station_id):

    conn = get_db_connection()
    event_id = _get_station_event_id(conn, station_id) or _get_active_event_id(conn)

    # ------------------------------------------------------------
    # [1110] ALLE RELEVANTEN ORDERS FÜR DIESE STATION
    # ------------------------------------------------------------
    # Keep paid orders out of station flow and only include station-relevant open items.
    orders = conn.execute("""
        SELECT DISTINCT
            o.id,
            o.order_number,
            oss.status,
            o.created_at
        FROM orders o
        JOIN order_station_status oss ON oss.order_id = o.id
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        JOIN station_categories sc ON sc.category_id = p.category_id
        WHERE oss.station_id = ?
          AND o.event_id = ?
          AND o.status != 'paid'
          AND sc.station_id = ?
          AND sc.event_id = ?
          AND oi.quantity_open > 0
        ORDER BY o.created_at ASC
    """, (station_id, event_id, station_id, event_id)).fetchall()
    order_map = {o["id"]: o for o in orders}
    order_ids_sorted = [o["id"] for o in orders]

    # ------------------------------------------------------------
    # [1120] BISHERIGE DISPLAY-SLOTS LADEN
    # ------------------------------------------------------------
    slots = conn.execute("""
        SELECT *
        FROM station_display
        WHERE station_id = ?
        ORDER BY position ASC
    """, (station_id,)).fetchall()
    # Remove stale slots not part of active station-relevant order set.
    for s in slots:
        if s["order_id"] not in order_map:
            conn.execute("""
                DELETE FROM station_display
                WHERE id = ?
            """, (s["id"],))

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

    # ------------------------------------------------------------
    # [1130] SLOTMANAGEMENT:
    # - locked/preparing bleibt fix
    # - offene/neu Karten rutschen in freie Positionen nach
    # - neue wartende Orders werden am Ende angehängt
    # ------------------------------------------------------------
    locked_slots = [s for s in slots if int(s["locked"] or 0) == 1]
    unlocked_slots = [s for s in slots if int(s["locked"] or 0) == 0]
    locked_positions = {s["position"] for s in locked_slots}

    # Re-pack existing unlocked cards to earliest non-locked positions
    # while preserving their current queue order.
    unlocked_slots_sorted = sorted(unlocked_slots, key=lambda x: x["position"])
    free_positions_for_unlocked = [p for p in range(1, 16) if p not in locked_positions]
    for idx, s in enumerate(unlocked_slots_sorted):
        if idx >= len(free_positions_for_unlocked):
            break
        new_pos = free_positions_for_unlocked[idx]
        if s["position"] != new_pos:
            conn.execute("""
                UPDATE station_display
                SET position = ?
                WHERE id = ?
            """, (new_pos, s["id"]))

    conn.commit()

    slots = conn.execute("""
        SELECT *
        FROM station_display
        WHERE station_id = ?
        ORDER BY position ASC
    """, (station_id,)).fetchall()

    displayed_ids = [s["order_id"] for s in slots]
    waiting_ids = [oid for oid in order_ids_sorted if oid not in displayed_ids]

    # Append waiting orders at the tail (not into early gaps).
    occupied_positions = {s["position"] for s in slots}
    tail_start = (max(occupied_positions) + 1) if occupied_positions else 1
    pos = tail_start
    for oid in waiting_ids:
        while pos <= 15 and pos in occupied_positions:
            pos += 1
        if pos > 15:
            break
        conn.execute("""
            INSERT INTO station_display (station_id, order_id, position)
            VALUES (?, ?, ?)
        """, (station_id, oid, pos))
        occupied_positions.add(pos)
        pos += 1

    conn.commit()
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
                COALESCE(oi.product_name, p.name) AS name,
                COALESCE(oi.unit_price, p.price) AS unit_price,
                oi.quantity_total,
                oi.quantity_open
            FROM order_items oi
            JOIN products p
                ON oi.product_id = p.id
            JOIN station_categories sc
                ON sc.category_id = p.category_id
            WHERE oi.order_id = ?
              AND sc.station_id = ?
              AND sc.event_id = ?
              AND oi.quantity_open > 0
            ORDER BY oi.id ASC
        """, (order_row["id"], station_id, event_id)).fetchall()

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
          AND sc.event_id = ?
          AND oi.quantity_open > 0
          AND o.event_id = ?
          AND o.status != 'paid'
    """, (station_id, event_id, event_id)).fetchone()["cnt"]

    shown_count = len([s for s in slots[:15] if s["order_id"] in order_map])
    waiting = max(0, open_station_orders - shown_count)

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

    event_id = _get_active_event_id(conn)

    row = conn.execute("""
        SELECT MAX(order_number) AS max_nr
        FROM orders
        WHERE event_id = ?
    """, (event_id,)).fetchone()

    next_number = (row["max_nr"] or 0) + 1

    cursor = conn.execute("""
        INSERT INTO orders (event_id, order_number, table_id, waiter_id, status)
        VALUES (?, ?, ?, ?, 'new')
    """, (
        event_id,
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
        SELECT category_id, price, name, event_id
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
          AND event_id = ?
    """, (product["category_id"], product["event_id"])).fetchall()

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
                unit_price,
                product_name,
                note,
                quantity_total,
                quantity_open,
                quantity_paid
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            order_id,
            data["product_id"],
            product["price"],
            product["name"],
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
    payment_type = data.get("payment_type", "paid")
    tab_id = data.get("tab_id")

    conn = get_db_connection()
    if payment_type not in ("paid", "tab"):
        conn.close()
        return jsonify({"error": "invalid payment_type"}), 400

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
        SELECT oi.*, COALESCE(oi.unit_price, p.price) AS price
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.id = ?
          AND oi.order_id = ?
    """, (order_item_id, order_id)).fetchone()

    if not item or item["quantity_open"] < quantity:
        conn.close()
        return jsonify({"error": "invalid"}), 400

    amount = item["price"] * quantity
    payment_amount = amount if payment_type == "paid" else 0.0

    order_row = conn.execute("""
        SELECT event_id, waiter_id, source, source_station_id
        FROM orders
        WHERE id = ?
    """, (order_id,)).fetchone()
    if not order_row:
        conn.close()
        return jsonify({"error": "order not found"}), 404

    if payment_type == "tab":
        if not tab_id:
            conn.close()
            return jsonify({"error": "tab_id required"}), 400
        tab = conn.execute("""
            SELECT id
            FROM tabs
            WHERE id = ?
              AND event_id = ?
              AND active = 1
        """, (tab_id, order_row["event_id"])).fetchone()
        if not tab:
            conn.close()
            return jsonify({"error": "tab not found"}), 404

    cursor = conn.execute("""
        INSERT INTO payments (order_id, amount, payment_type)
        VALUES (?, ?, ?)
    """, (order_id, payment_amount, payment_type))

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

    if payment_type == "tab":
        if order_row["source"] == "station" and order_row["source_station_id"]:
            conn.execute("""
                INSERT INTO tab_entries (
                    tab_id, order_id, order_item_id, quantity, unit_price, amount,
                    created_by_role, created_by_user_id, created_by_station_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'station', NULL, ?)
            """, (
                tab_id, order_id, order_item_id, quantity, float(item["price"]), amount,
                int(order_row["source_station_id"]),
            ))
        else:
            conn.execute("""
                INSERT INTO tab_entries (
                    tab_id, order_id, order_item_id, quantity, unit_price, amount,
                    created_by_role, created_by_user_id, created_by_station_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'waiter', ?, NULL)
            """, (
                tab_id, order_id, order_item_id, quantity, float(item["price"]), amount,
                order_row["waiter_id"],
            ))

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

    return jsonify({"paid_amount": payment_amount, "payment_type": payment_type, "tab_amount": amount if payment_type == "tab" else 0})


@orders_bp.route("/orders/<int:order_id>/pay-internal", methods=["POST"])
def pay_internal(order_id):
    conn = get_db_connection()

    order = conn.execute("""
        SELECT id
        FROM orders
        WHERE id = ?
    """, (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"error": "not found"}), 404

    open_rows = conn.execute("""
        SELECT oi.id, oi.quantity_open
        FROM order_items oi
        WHERE oi.order_id = ?
          AND oi.quantity_open > 0
    """, (order_id,)).fetchall()

    if not open_rows:
        conn.close()
        return jsonify({"status": "nothing open"}), 200

    cursor = conn.execute("""
        INSERT INTO payments (order_id, amount, payment_type)
        VALUES (?, 0, 'internal')
    """, (order_id,))
    payment_id = cursor.lastrowid

    for r in open_rows:
        qty = int(r["quantity_open"])
        conn.execute("""
            INSERT INTO payment_items (payment_id, order_item_id, quantity)
            VALUES (?, ?, ?)
        """, (payment_id, r["id"], qty))
        conn.execute("""
            UPDATE order_items
            SET quantity_paid = quantity_paid + ?,
                quantity_open = 0
            WHERE id = ?
        """, (qty, r["id"]))

    conn.execute("""
        UPDATE orders
        SET status = 'paid'
        WHERE id = ?
    """, (order_id,))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "payment_type": "internal"})


@orders_bp.route("/station/<int:station_id>/products")
def station_products(station_id):
    conn = get_db_connection()
    event_id = _get_station_event_id(conn, station_id) or _get_active_event_id(conn)

    rows = conn.execute("""
        SELECT
            p.id,
            p.name,
            p.price,
            p.category_id,
            c.name AS category_name
        FROM products p
        JOIN categories c ON c.id = p.category_id
        JOIN station_categories sc ON sc.category_id = p.category_id
        WHERE sc.station_id = ?
          AND sc.event_id = ?
          AND p.event_id = ?
          AND p.active = 1
        ORDER BY c.name ASC, p.name ASC
    """, (station_id, event_id, event_id)).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])


@orders_bp.route("/station/<int:station_id>/orders", methods=["POST"])
def station_create_order(station_id):
    data = request.json or {}
    items = data.get("items") or []
    if not items:
        return jsonify({"error": "items required"}), 400

    conn = get_db_connection()
    event_id = _get_station_event_id(conn, station_id) or _get_active_event_id(conn)

    row = conn.execute("""
        SELECT MAX(order_number) AS max_nr
        FROM orders
        WHERE event_id = ?
    """, (event_id,)).fetchone()
    next_number = (row["max_nr"] or 0) + 1

    cursor = conn.execute("""
        INSERT INTO orders (
            event_id, order_number, table_id, waiter_id, status, source, source_station_id
        ) VALUES (?, ?, NULL, NULL, 'new', 'station', ?)
    """, (event_id, next_number, station_id))
    order_id = cursor.lastrowid

    station_exists = False
    for item in items:
        product_id = item.get("product_id")
        qty = int(item.get("quantity", 1))
        if not product_id or qty <= 0:
            continue

        product = conn.execute("""
            SELECT p.id, p.name, p.price, p.category_id
            FROM products p
            JOIN station_categories sc ON sc.category_id = p.category_id
            WHERE p.id = ?
              AND p.event_id = ?
              AND sc.station_id = ?
              AND sc.event_id = ?
        """, (product_id, event_id, station_id, event_id)).fetchone()

        if not product:
            continue

        conn.execute("""
            INSERT INTO order_items (
                order_id, product_id, unit_price, product_name, note,
                quantity_total, quantity_open, quantity_paid
            ) VALUES (?, ?, ?, ?, '', ?, ?, 0)
        """, (order_id, product["id"], product["price"], product["name"], qty, qty))

        exists = conn.execute("""
            SELECT 1
            FROM order_station_status
            WHERE order_id = ? AND station_id = ?
        """, (order_id, station_id)).fetchone()
        if not exists:
            conn.execute("""
                INSERT INTO order_station_status (order_id, station_id, status)
                VALUES (?, ?, 'new')
            """, (order_id, station_id))
        station_exists = True

    if not station_exists:
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        return jsonify({"error": "no valid station items"}), 400

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "order_id": order_id})


@orders_bp.route("/station/<int:station_id>/orders/open")
def station_open_orders(station_id):
    conn = get_db_connection()
    event_id = _get_station_event_id(conn, station_id) or _get_active_event_id(conn)

    rows = conn.execute("""
        SELECT DISTINCT o.id, o.order_number, o.created_at, o.source,
               COALESCE(t.name, 'Theke Direktverkauf') AS table_name
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        JOIN station_categories sc ON sc.category_id = p.category_id
        LEFT JOIN tables t ON t.id = o.table_id
        WHERE sc.station_id = ?
          AND sc.event_id = ?
          AND o.event_id = ?
          AND o.source = 'station'
          AND o.source_station_id = ?
          AND o.status != 'paid'
          AND oi.quantity_open > 0
        ORDER BY o.created_at ASC
    """, (station_id, event_id, event_id, station_id)).fetchall()

    result = []
    for o in rows:
        items = conn.execute("""
            SELECT oi.id, COALESCE(oi.product_name, p.name) AS name,
                   COALESCE(oi.unit_price, p.price) AS price,
                   oi.quantity_open
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            JOIN station_categories sc ON sc.category_id = p.category_id
            WHERE oi.order_id = ?
              AND sc.station_id = ?
              AND sc.event_id = ?
              AND oi.quantity_open > 0
            ORDER BY oi.id ASC
        """, (o["id"], station_id, event_id)).fetchall()
        total = sum(float(i["price"]) * int(i["quantity_open"]) for i in items)
        result.append({
            "order_id": o["id"],
            "order_number": o["order_number"],
            "source": o["source"],
            "table_name": o["table_name"],
            "created_at": o["created_at"],
            "total_open": total,
            "items": [dict(i) for i in items],
        })

    conn.close()
    return jsonify(result)


@orders_bp.route("/station/<int:station_id>/orders/<int:order_id>/settle", methods=["POST"])
def station_settle_order(station_id, order_id):
    data = request.json or {}
    payment_type = data.get("payment_type", "paid")
    tab_id = data.get("tab_id")
    if payment_type not in ("paid", "internal", "tab"):
        return jsonify({"error": "invalid payment_type"}), 400

    conn = get_db_connection()
    event_id = _get_station_event_id(conn, station_id) or _get_active_event_id(conn)

    # Only allow station cashier to settle station-created orders of this station.
    order_meta = conn.execute("""
        SELECT source, source_station_id
        FROM orders
        WHERE id = ?
          AND event_id = ?
    """, (order_id, event_id)).fetchone()
    if not order_meta:
        conn.close()
        return jsonify({"error": "order not found"}), 404
    if order_meta["source"] != "station" or int(order_meta["source_station_id"] or 0) != int(station_id):
        conn.close()
        return jsonify({"error": "forbidden"}), 403

    item_rows = conn.execute("""
        SELECT oi.id, oi.quantity_open, COALESCE(oi.unit_price, p.price) AS price
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        JOIN station_categories sc ON sc.category_id = p.category_id
        JOIN orders o ON o.id = oi.order_id
        WHERE oi.order_id = ?
          AND sc.station_id = ?
          AND sc.event_id = ?
          AND o.event_id = ?
          AND oi.quantity_open > 0
    """, (order_id, station_id, event_id, event_id)).fetchall()

    if not item_rows:
        conn.close()
        return jsonify({"status": "nothing open"}), 200

    order_row = conn.execute("""
        SELECT event_id
        FROM orders
        WHERE id = ?
    """, (order_id,)).fetchone()
    if not order_row:
        conn.close()
        return jsonify({"error": "order not found"}), 404

    if payment_type == "tab":
        if not tab_id:
            conn.close()
            return jsonify({"error": "tab_id required"}), 400
        tab = conn.execute("""
            SELECT id
            FROM tabs
            WHERE id = ?
              AND event_id = ?
              AND active = 1
        """, (tab_id, order_row["event_id"])).fetchone()
        if not tab:
            conn.close()
            return jsonify({"error": "tab not found"}), 404

    amount_raw = sum(
        float(r["price"]) * int(r["quantity_open"]) for r in item_rows
    )
    amount = 0.0 if payment_type in ("internal", "tab") else amount_raw

    cursor = conn.execute("""
        INSERT INTO payments (order_id, amount, payment_type)
        VALUES (?, ?, ?)
    """, (order_id, amount, payment_type))
    payment_id = cursor.lastrowid

    for r in item_rows:
        qty = int(r["quantity_open"])
        conn.execute("""
            INSERT INTO payment_items (payment_id, order_item_id, quantity)
            VALUES (?, ?, ?)
        """, (payment_id, r["id"], qty))
        if payment_type == "tab":
            conn.execute("""
                INSERT INTO tab_entries (
                    tab_id, order_id, order_item_id, quantity, unit_price, amount,
                    created_by_role, created_by_user_id, created_by_station_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'station', NULL, ?)
            """, (
                tab_id, order_id, r["id"], qty, float(r["price"]), float(r["price"]) * qty, station_id
            ))
        conn.execute("""
            UPDATE order_items
            SET quantity_paid = quantity_paid + ?,
                quantity_open = 0
            WHERE id = ?
        """, (qty, r["id"]))

    remaining = conn.execute("""
        SELECT COALESCE(SUM(quantity_open), 0) AS open_sum
        FROM order_items
        WHERE order_id = ?
    """, (order_id,)).fetchone()
    if int(remaining["open_sum"]) == 0:
        conn.execute("UPDATE orders SET status='paid' WHERE id = ?", (order_id,))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "payment_type": payment_type, "amount": amount})


@orders_bp.route("/tabs", methods=["GET", "POST"])
def tabs():
    conn = get_db_connection()
    station_id = request.args.get("station_id", type=int)
    if station_id:
        event_id = _get_station_event_id(conn, station_id) or _get_active_event_id(conn)
    else:
        event_id = request.args.get("event_id", type=int) or _get_active_event_id(conn)

    if request.method == "POST":
        data = request.json or {}
        name = (data.get("name") or "").strip()
        if not name:
            conn.close()
            return jsonify({"error": "name required"}), 400
        row = conn.execute("""
            INSERT INTO tabs (event_id, name, active)
            VALUES (?, ?, 1)
        """, (event_id, name))
        conn.commit()
        tab_id = row.lastrowid
        conn.close()
        return jsonify({"status": "ok", "tab_id": tab_id})

    result = _list_tabs_for_event(conn, event_id)
    conn.close()
    return jsonify(result)


@orders_bp.route("/tabs/<int:tab_id>/pay", methods=["POST"])
def pay_tab(tab_id: int):
    data = request.json or {}
    amount = data.get("amount")
    created_by_role = data.get("created_by_role") or "waiter"
    created_by_user_id = data.get("created_by_user_id")
    created_by_station_id = data.get("created_by_station_id")

    conn = get_db_connection()
    event_id = request.args.get("event_id", type=int) or _get_active_event_id(conn)

    tab = conn.execute("""
        SELECT id
        FROM tabs
        WHERE id = ?
          AND event_id = ?
          AND active = 1
    """, (tab_id, event_id)).fetchone()
    if not tab:
        conn.close()
        return jsonify({"error": "tab not found"}), 404

    bal_sql = sql_tab_open_balance("t")
    bal_row = conn.execute(f"""
        SELECT {bal_sql} AS balance
        FROM tabs t
        WHERE t.id = ?
    """, (tab_id,)).fetchone()
    balance = max(0.0, float(bal_row["balance"] or 0) if bal_row else 0.0)
    if balance <= 0:
        conn.close()
        return jsonify({"status": "nothing open", "balance": balance}), 200

    if amount is None:
        pay_amount = balance
    else:
        try:
            pay_amount = float(amount)
        except Exception:
            conn.close()
            return jsonify({"error": "invalid amount"}), 400
        if pay_amount <= 0:
            conn.close()
            return jsonify({"error": "invalid amount"}), 400
        pay_amount = min(pay_amount, balance)

    conn.execute("""
        INSERT INTO tab_payments (tab_id, amount, created_by_role, created_by_user_id, created_by_station_id)
        VALUES (?, ?, ?, ?, ?)
    """, (tab_id, pay_amount, created_by_role, created_by_user_id, created_by_station_id))
    conn.commit()

    new_balance_row = conn.execute(f"""
        SELECT {bal_sql} AS balance
        FROM tabs t
        WHERE t.id = ?
    """, (tab_id,)).fetchone()
    new_balance = max(0.0, float(new_balance_row["balance"] or 0) if new_balance_row else 0.0)

    conn.close()
    return jsonify({"status": "ok", "paid_amount": pay_amount, "balance": new_balance})


@orders_bp.route("/tabs/<int:tab_id>/summary")
def tab_summary(tab_id: int):
    conn = get_db_connection()
    event_id = request.args.get("event_id", type=int) or _get_active_event_id(conn)
    bal = sql_tab_open_balance("t")
    row = conn.execute(f"""
        SELECT
            t.id,
            t.name,
            COALESCE((SELECT SUM(te.amount) FROM tab_entries te WHERE te.tab_id = t.id), 0) AS entries_amount,
            COALESCE((SELECT SUM(tp.amount) FROM tab_payments tp WHERE tp.tab_id = t.id), 0) AS payments_amount,
            {bal} AS balance
        FROM tabs t
        WHERE t.id = ?
          AND t.event_id = ?
          AND t.active = 1
    """, (tab_id, event_id)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "tab not found"}), 404
    d = dict(row)
    d["balance"] = max(0.0, float(d.get("balance") or 0))
    conn.close()
    return jsonify(d)


@orders_bp.route("/tabs/<int:tab_id>/items")
def tab_items(tab_id: int):
    conn = get_db_connection()
    event_id = request.args.get("event_id", type=int) or _get_active_event_id(conn)
    tab = conn.execute("""
        SELECT id, name
        FROM tabs
        WHERE id = ?
          AND event_id = ?
          AND active = 1
    """, (tab_id, event_id)).fetchone()
    if not tab:
        conn.close()
        return jsonify({"error": "tab not found"}), 404

    rows = conn.execute("""
        SELECT
            te.id AS tab_entry_id,
            te.order_id,
            te.order_item_id,
            COALESCE(oi.product_name, p.name, 'Unbekannt') AS item_name,
            COALESCE(te.unit_price, oi.unit_price, p.price, 0) AS unit_price,
            te.quantity AS quantity_total,
            COALESCE((
                SELECT SUM(tpi.quantity)
                FROM tab_payment_items tpi
                WHERE tpi.tab_entry_id = te.id
            ), 0) AS quantity_paid
        FROM tab_entries te
        LEFT JOIN order_items oi ON oi.id = te.order_item_id
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE te.tab_id = ?
        ORDER BY te.id ASC
    """, (tab_id,)).fetchall()

    items = []
    for r in rows:
        qty_total = int(r["quantity_total"] or 0)
        qty_paid = int(r["quantity_paid"] or 0)
        qty_open = max(0, qty_total - qty_paid)
        if qty_open <= 0:
            continue
        unit_price = float(r["unit_price"] or 0)
        items.append({
            "tab_entry_id": int(r["tab_entry_id"]),
            "order_id": r["order_id"],
            "order_item_id": r["order_item_id"],
            "name": r["item_name"],
            "unit_price": unit_price,
            "quantity_total": qty_total,
            "quantity_paid": qty_paid,
            "quantity_open": qty_open,
            "line_open": unit_price * qty_open
        })

    conn.close()
    return jsonify({
        "tab_id": int(tab["id"]),
        "tab_name": tab["name"],
        "items": items
    })


@orders_bp.route("/tabs/<int:tab_id>/pay-items", methods=["POST"])
def pay_tab_items(tab_id: int):
    data = request.json or {}
    entries = data.get("entries") or []
    created_by_role = data.get("created_by_role") or "waiter"
    created_by_user_id = data.get("created_by_user_id")
    created_by_station_id = data.get("created_by_station_id")
    if not isinstance(entries, list) or not entries:
        return jsonify({"error": "entries required"}), 400

    conn = get_db_connection()
    event_id = request.args.get("event_id", type=int) or _get_active_event_id(conn)
    tab = conn.execute("""
        SELECT id
        FROM tabs
        WHERE id = ?
          AND event_id = ?
          AND active = 1
    """, (tab_id, event_id)).fetchone()
    if not tab:
        conn.close()
        return jsonify({"error": "tab not found"}), 404

    total_amount = 0.0
    resolved = []
    for e in entries:
        try:
            tab_entry_id = int(e.get("tab_entry_id"))
            qty = int(e.get("quantity"))
        except Exception:
            conn.close()
            return jsonify({"error": "invalid entry payload"}), 400
        if qty <= 0:
            continue
        row = conn.execute("""
            SELECT
                te.id,
                te.quantity AS quantity_total,
                COALESCE(te.unit_price, oi.unit_price, p.price, 0) AS unit_price,
                COALESCE((
                    SELECT SUM(tpi.quantity)
                    FROM tab_payment_items tpi
                    WHERE tpi.tab_entry_id = te.id
                ), 0) AS quantity_paid
            FROM tab_entries te
            LEFT JOIN order_items oi ON oi.id = te.order_item_id
            LEFT JOIN products p ON p.id = oi.product_id
            WHERE te.id = ?
              AND te.tab_id = ?
        """, (tab_entry_id, tab_id)).fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "tab entry not found"}), 404

        open_qty = max(0, int(row["quantity_total"] or 0) - int(row["quantity_paid"] or 0))
        use_qty = min(open_qty, qty)
        if use_qty <= 0:
            continue
        unit_price = float(row["unit_price"] or 0)
        amount = unit_price * use_qty
        total_amount += amount
        resolved.append((int(row["id"]), use_qty, amount))

    if not resolved:
        conn.close()
        return jsonify({"error": "nothing to pay"}), 400

    cur = conn.execute("""
        INSERT INTO tab_payments (tab_id, amount, created_by_role, created_by_user_id, created_by_station_id)
        VALUES (?, ?, ?, ?, ?)
    """, (tab_id, total_amount, created_by_role, created_by_user_id, created_by_station_id))
    payment_id = cur.lastrowid

    for tab_entry_id, qty, amount in resolved:
        conn.execute("""
            INSERT INTO tab_payment_items (payment_id, tab_entry_id, quantity, amount)
            VALUES (?, ?, ?, ?)
        """, (payment_id, tab_entry_id, qty, amount))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "paid_amount": total_amount})


@orders_bp.route("/tabs/transfer-items", methods=["POST"])
def transfer_tab_items():
    data = request.json or {}
    source_tab_id = data.get("source_tab_id")
    target_tab_id = data.get("target_tab_id")
    entries = data.get("entries") or []
    created_by_role = data.get("created_by_role") or "waiter"
    created_by_user_id = data.get("created_by_user_id")
    created_by_station_id = data.get("created_by_station_id")

    try:
        source_tab_id = int(source_tab_id)
        target_tab_id = int(target_tab_id)
    except Exception:
        return jsonify({"error": "invalid source/target"}), 400
    if source_tab_id <= 0 or target_tab_id <= 0 or source_tab_id == target_tab_id:
        return jsonify({"error": "invalid source/target"}), 400
    if not isinstance(entries, list) or not entries:
        return jsonify({"error": "entries required"}), 400

    conn = get_db_connection()
    event_id = request.args.get("event_id", type=int) or _get_active_event_id(conn)
    src = conn.execute("SELECT id FROM tabs WHERE id=? AND event_id=? AND active=1", (source_tab_id, event_id)).fetchone()
    dst = conn.execute("SELECT id FROM tabs WHERE id=? AND event_id=? AND active=1", (target_tab_id, event_id)).fetchone()
    if not src or not dst:
        conn.close()
        return jsonify({"error": "tab not found"}), 404

    total_amount = 0.0
    resolved = []
    for e in entries:
        try:
            tab_entry_id = int(e.get("tab_entry_id"))
            qty = int(e.get("quantity"))
        except Exception:
            conn.close()
            return jsonify({"error": "invalid entry payload"}), 400
        if qty <= 0:
            continue
        row = conn.execute("""
            SELECT
                te.id,
                te.order_id,
                te.order_item_id,
                te.quantity AS quantity_total,
                COALESCE(te.unit_price, oi.unit_price, p.price, 0) AS unit_price,
                COALESCE((
                    SELECT SUM(tpi.quantity)
                    FROM tab_payment_items tpi
                    WHERE tpi.tab_entry_id = te.id
                ), 0) AS quantity_paid
            FROM tab_entries te
            LEFT JOIN order_items oi ON oi.id = te.order_item_id
            LEFT JOIN products p ON p.id = oi.product_id
            WHERE te.id = ?
              AND te.tab_id = ?
        """, (tab_entry_id, source_tab_id)).fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "tab entry not found"}), 404

        open_qty = max(0, int(row["quantity_total"] or 0) - int(row["quantity_paid"] or 0))
        use_qty = min(open_qty, qty)
        if use_qty <= 0:
            continue
        unit_price = float(row["unit_price"] or 0)
        amount = unit_price * use_qty
        total_amount += amount
        resolved.append({
            "tab_entry_id": int(row["id"]),
            "order_id": row["order_id"],
            "order_item_id": row["order_item_id"],
            "quantity": use_qty,
            "unit_price": unit_price,
            "amount": amount
        })

    if not resolved:
        conn.close()
        return jsonify({"error": "nothing to transfer"}), 400

    cur = conn.execute("""
        INSERT INTO tab_payments (tab_id, amount, created_by_role, created_by_user_id, created_by_station_id)
        VALUES (?, ?, ?, ?, ?)
    """, (source_tab_id, total_amount, created_by_role, created_by_user_id, created_by_station_id))
    payment_id = cur.lastrowid

    for r in resolved:
        conn.execute("""
            INSERT INTO tab_payment_items (payment_id, tab_entry_id, quantity, amount)
            VALUES (?, ?, ?, ?)
        """, (payment_id, r["tab_entry_id"], r["quantity"], r["amount"]))
        conn.execute("""
            INSERT INTO tab_entries (
                tab_id, order_id, order_item_id, quantity, unit_price, amount,
                created_by_role, created_by_user_id, created_by_station_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            target_tab_id,
            r["order_id"],
            r["order_item_id"],
            r["quantity"],
            r["unit_price"],
            r["amount"],
            created_by_role,
            created_by_user_id,
            created_by_station_id
        ))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "moved_amount": total_amount})


@orders_bp.route("/tabs/transfer", methods=["POST"])
def transfer_tab_balance():
    data = request.json or {}
    source_tab_id = data.get("source_tab_id")
    target_tab_id = data.get("target_tab_id")
    amount = data.get("amount")
    created_by_role = data.get("created_by_role") or "waiter"
    created_by_user_id = data.get("created_by_user_id")
    created_by_station_id = data.get("created_by_station_id")

    try:
        source_tab_id = int(source_tab_id)
        target_tab_id = int(target_tab_id)
        amount = float(amount)
    except Exception:
        return jsonify({"error": "invalid payload"}), 400

    if source_tab_id <= 0 or target_tab_id <= 0 or source_tab_id == target_tab_id:
        return jsonify({"error": "invalid source/target"}), 400
    if amount <= 0:
        return jsonify({"error": "invalid amount"}), 400

    conn = get_db_connection()
    event_id = request.args.get("event_id", type=int) or _get_active_event_id(conn)

    src = conn.execute("""
        SELECT id, name
        FROM tabs
        WHERE id = ?
          AND event_id = ?
          AND active = 1
    """, (source_tab_id, event_id)).fetchone()
    dst = conn.execute("""
        SELECT id, name
        FROM tabs
        WHERE id = ?
          AND event_id = ?
          AND active = 1
    """, (target_tab_id, event_id)).fetchone()
    if not src or not dst:
        conn.close()
        return jsonify({"error": "tab not found"}), 404

    bal_sql = sql_tab_open_balance("t")
    src_bal_row = conn.execute(f"""
        SELECT {bal_sql} AS balance
        FROM tabs t
        WHERE t.id = ?
    """, (source_tab_id,)).fetchone()
    src_balance = float(src_bal_row["balance"] or 0) if src_bal_row else 0.0
    if src_balance <= 0:
        conn.close()
        return jsonify({"error": "source tab has no open balance"}), 400

    move_amount = min(amount, src_balance)

    # Reduce source tab by recording payment-equivalent transfer out.
    conn.execute("""
        INSERT INTO tab_payments (tab_id, amount, created_by_role, created_by_user_id, created_by_station_id)
        VALUES (?, ?, ?, ?, ?)
    """, (source_tab_id, move_amount, created_by_role, created_by_user_id, created_by_station_id))

    # Increase target tab by recording transfer in as a tab entry.
    conn.execute("""
        INSERT INTO tab_entries (
            tab_id, order_id, order_item_id, quantity, unit_price, amount,
            created_by_role, created_by_user_id, created_by_station_id
        ) VALUES (?, NULL, NULL, 1, ?, ?, ?, ?, ?)
    """, (target_tab_id, move_amount, move_amount, created_by_role, created_by_user_id, created_by_station_id))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "moved_amount": move_amount})

# ============================================================
# [1600] ORDER TOTALS
# ============================================================
@orders_bp.route("/orders/<int:order_id>/totals")
def order_totals(order_id):
    conn = get_db_connection()

    rows = conn.execute("""
        SELECT oi.quantity_total, oi.quantity_open,
               COALESCE(oi.unit_price, p.price) AS price
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
        SELECT oi.id,
               COALESCE(oi.product_name, p.name) AS name,
               COALESCE(oi.unit_price, p.price) AS price,
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
    payload = _order_status_payload(conn, order_id)
    conn.close()
    return jsonify(payload)


@orders_bp.route("/orders/status-board")
def orders_status_board():
    conn = get_db_connection()
    event_id = _get_active_event_id(conn)

    orders = conn.execute("""
        SELECT
            o.id,
            o.order_number,
            COALESCE(t.name, 'Ohne Tisch') AS table_name,
            COALESCE(u.name, 'Unbekannt') AS waiter_name
        FROM orders o
        LEFT JOIN tables t ON t.id = o.table_id
        LEFT JOIN users u ON u.id = o.waiter_id
        WHERE o.event_id = ?
          AND o.status != 'paid'
          AND EXISTS (
            SELECT 1
            FROM order_items oi
            WHERE oi.order_id = o.id
              AND oi.quantity_open > 0
          )
        ORDER BY o.created_at ASC, o.id ASC
        LIMIT 200
    """, (event_id,)).fetchall()

    out = []
    for o in orders:
        order_id = int(o["id"])

        items = conn.execute("""
            SELECT
                COALESCE(oi.product_name, p.name) AS name,
                COALESCE(oi.unit_price, p.price, 0) AS price,
                oi.quantity_open
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?
              AND oi.quantity_open > 0
            ORDER BY oi.id ASC
        """, (order_id,)).fetchall()

        station_stats = conn.execute("""
            SELECT status
            FROM order_station_status
            WHERE order_id = ?
        """, (order_id,)).fetchall()
        station_total = len(station_stats)
        station_ready = sum(1 for s in station_stats if str(s["status"] or "").lower() == "ready")

        st_payload = _order_status_payload(conn, order_id)

        item_rows = []
        total_open = 0.0
        for i in items:
            qty = int(i["quantity_open"] or 0)
            price = float(i["price"] or 0)
            total_open += qty * price
            item_rows.append({
                "name": i["name"],
                "price": price,
                "quantity_open": qty
            })

        out.append({
            "order_id": order_id,
            "order_number": int(o["order_number"]),
            "table_name": o["table_name"],
            "waiter_name": o["waiter_name"],
            "items": item_rows,
            "total_open": total_open,
            "station_total": station_total,
            "station_ready": station_ready,
            "all_ready": station_total > 0 and station_ready == station_total,
            "status": st_payload["status"],
            "status_key": st_payload["status_key"],
        })

    conn.close()
    return jsonify(out)
