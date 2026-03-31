from flask import Blueprint, request, jsonify
from db import (
    get_db_connection,
    get_active_event_id,
    sql_tab_open_balance,
    purge_orders_for_event,
    purge_database_for_live,
)

admin_bp = Blueprint('admin', __name__)

# ============================================================
# [0900] EVENTS + STATS
# ============================================================
@admin_bp.route("/admin/events", methods=["GET", "POST"])
def events():
    conn = get_db_connection()

    if request.method == "POST":
        data = request.json or {}
        name = (data.get("name") or "").strip()
        template_event_id = data.get("template_event_id")

        if not name:
            conn.close()
            return jsonify({"error": "name required"}), 400

        # Create as closed by default; user can activate explicitly.
        cursor = conn.execute("""
            INSERT INTO events (name, status)
            VALUES (?, 'closed')
        """, (name,))
        new_id = cursor.lastrowid

        # Template support: copy configuration from an existing event if provided.
        if template_event_id:
            # Categories
            cat_rows = conn.execute("""
                SELECT id, name
                FROM categories
                WHERE event_id = ?
                ORDER BY id ASC
            """, (template_event_id,)).fetchall()

            cat_map = {}
            for c in cat_rows:
                cur = conn.execute("""
                    INSERT INTO categories (event_id, name)
                    VALUES (?, ?)
                """, (new_id, c["name"]))
                cat_map[c["id"]] = cur.lastrowid

            # Products
            prod_rows = conn.execute("""
                SELECT id, name, price, category_id, active
                FROM products
                WHERE event_id = ?
                ORDER BY id ASC
            """, (template_event_id,)).fetchall()

            for p in prod_rows:
                conn.execute("""
                    INSERT INTO products (event_id, name, price, category_id, active)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    new_id,
                    p["name"],
                    p["price"],
                    cat_map.get(p["category_id"]),
                    p["active"],
                ))

            # Tables
            table_rows = conn.execute("""
                SELECT id, name, active
                FROM tables
                WHERE event_id = ?
                ORDER BY id ASC
            """, (template_event_id,)).fetchall()
            table_map = {}
            for t in table_rows:
                cur = conn.execute("""
                    INSERT INTO tables (event_id, name, active)
                    VALUES (?, ?, ?)
                """, (new_id, t["name"], t["active"]))
                table_map[t["id"]] = cur.lastrowid

            # Users (waiter + station; keep pins)
            user_rows = conn.execute("""
                SELECT id, name, pin, role, active
                FROM users
                WHERE event_id = ?
                ORDER BY id ASC
            """, (template_event_id,)).fetchall()
            user_map = {}
            for u in user_rows:
                cur = conn.execute("""
                    INSERT INTO users (event_id, name, pin, role, active)
                    VALUES (?, ?, ?, ?, ?)
                """, (new_id, u["name"], u["pin"], u["role"], u["active"]))
                user_map[u["id"]] = cur.lastrowid

            # Waiter -> tables assignments
            wt_rows = conn.execute("""
                SELECT waiter_id, table_id
                FROM waiter_tables
                WHERE event_id = ?
            """, (template_event_id,)).fetchall()
            for r in wt_rows:
                new_waiter = user_map.get(r["waiter_id"])
                new_table = table_map.get(r["table_id"])
                if new_waiter and new_table:
                    conn.execute("""
                        INSERT INTO waiter_tables (event_id, waiter_id, table_id)
                        VALUES (?, ?, ?)
                    """, (new_id, new_waiter, new_table))

            # Station -> categories assignments
            sc_rows = conn.execute("""
                SELECT station_id, category_id
                FROM station_categories
                WHERE event_id = ?
            """, (template_event_id,)).fetchall()
            for r in sc_rows:
                new_station = user_map.get(r["station_id"])
                new_cat = cat_map.get(r["category_id"])
                if new_station and new_cat:
                    conn.execute("""
                        INSERT INTO station_categories (event_id, station_id, category_id)
                        VALUES (?, ?, ?)
                    """, (new_id, new_station, new_cat))

        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "event_id": new_id})

    active = conn.execute("""
        SELECT id, name, status, starts_at, ends_at
        FROM events
        WHERE status = 'active'
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    tab_bal = sql_tab_open_balance("t")
    rows = conn.execute(f"""
        SELECT
            e.id,
            e.name,
            e.status,
            e.starts_at,
            e.ends_at,
            COALESCE((
                SELECT SUM(oi.quantity_open * COALESCE(oi.unit_price, p.price))
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                JOIN products p ON p.id = oi.product_id
                WHERE o.event_id = e.id
            ), 0) AS open_orders_amount,
            COALESCE((
                SELECT SUM({tab_bal})
                FROM tabs t
                WHERE t.event_id = e.id
                  AND t.active = 1
            ), 0) AS open_tabs_amount
        FROM events e
        ORDER BY id DESC
        LIMIT 200
    """).fetchall()

    conn.close()
    events_out = []
    for r in rows:
        d = dict(r)
        open_total = float(d.get("open_orders_amount") or 0) + float(d.get("open_tabs_amount") or 0)
        d["billing_status"] = "Abgerechnet" if open_total <= 0.0001 else "Zahlungen offen"
        d["open_total_amount"] = open_total
        events_out.append(d)

    return jsonify({
        "active_event": dict(active) if active else None,
        "events": events_out
    })


@admin_bp.route("/admin/events/activate", methods=["POST"])
def activate_event():
    data = request.json or {}
    event_id = data.get("event_id")
    if not event_id:
        return jsonify({"error": "event_id required"}), 400

    conn = get_db_connection()

    # Close any currently active event.
    conn.execute("""
        UPDATE events
        SET status = 'closed',
            ends_at = COALESCE(ends_at, CURRENT_TIMESTAMP)
        WHERE status = 'active'
    """)

    # Activate selected event (reopens if previously closed).
    conn.execute("""
        UPDATE events
        SET status = 'active',
            starts_at = COALESCE(starts_at, CURRENT_TIMESTAMP),
            ends_at = NULL
        WHERE id = ?
    """, (event_id,))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@admin_bp.route("/admin/events/close", methods=["POST"])
def close_event():
    data = request.json or {}
    event_id = data.get("event_id")

    conn = get_db_connection()
    if not event_id:
        row = conn.execute("""
            SELECT id
            FROM events
            WHERE status = 'active'
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()
        event_id = row["id"] if row else None

    if not event_id:
        conn.close()
        return jsonify({"error": "no active event"}), 400

    open_orders_amount = conn.execute("""
        SELECT COALESCE(SUM(oi.quantity_open * COALESCE(oi.unit_price, p.price)), 0) AS v
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.event_id = ?
    """, (event_id,)).fetchone()["v"]

    tab_bal = sql_tab_open_balance("t")
    open_tabs_amount = conn.execute(f"""
        SELECT COALESCE(SUM({tab_bal}), 0) AS v
        FROM tabs t
        WHERE t.event_id = ?
          AND t.active = 1
    """, (event_id,)).fetchone()["v"]

    open_total = float(open_orders_amount or 0) + float(open_tabs_amount or 0)
    if open_total > 0.0001:
        conn.close()
        return jsonify({
            "error": "Event kann nicht geschlossen werden: Zahlungen offen",
            "open_orders_amount": float(open_orders_amount or 0),
            "open_tabs_amount": float(open_tabs_amount or 0),
            "open_total_amount": open_total
        }), 400

    conn.execute("""
        UPDATE events
        SET status = 'closed',
            ends_at = COALESCE(ends_at, CURRENT_TIMESTAMP)
        WHERE id = ?
    """, (event_id,))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@admin_bp.route("/admin/events/update", methods=["POST"])
def update_event():
    data = request.json or {}
    event_id = data.get("event_id")
    name = (data.get("name") or "").strip()
    if not event_id or not name:
        return jsonify({"error": "event_id and name required"}), 400

    conn = get_db_connection()
    conn.execute("""
        UPDATE events
        SET name = ?
        WHERE id = ?
    """, (name, event_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@admin_bp.route("/admin/events/duplicate", methods=["POST"])
def duplicate_event():
    data = request.json or {}
    source_event_id = data.get("source_event_id")
    name = (data.get("name") or "").strip()

    if not source_event_id:
        return jsonify({"error": "source_event_id required"}), 400

    conn = get_db_connection()
    src = conn.execute("""
        SELECT name
        FROM events
        WHERE id = ?
    """, (source_event_id,)).fetchone()

    if not src:
        conn.close()
        return jsonify({"error": "not found"}), 404

    new_name = name or (str(src["name"]) + " (Kopie)")
    cursor = conn.execute("""
        INSERT INTO events (name, status)
        VALUES (?, 'closed')
    """, (new_name,))
    new_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "event_id": new_id})


@admin_bp.route("/admin/events/clear-orders", methods=["POST"])
def clear_event_orders():
    """
    - live_reset: alle Orders + Stammdaten aller Events, neues leeres Event (new_event_name).
    - sonst: alle Orders eines Events (event_id oder aktives Event).
    """
    data = request.json or {}
    if data.get("live_reset"):
        conn = get_db_connection()
        name = (data.get("new_event_name") or "Live").strip() or "Live"
        deleted, new_eid = purge_database_for_live(conn, name)
        conn.close()
        return jsonify(
            {
                "status": "ok",
                "live_reset": True,
                "deleted_orders": deleted,
                "event_id": new_eid,
                "event_name": name,
            }
        )

    event_id = data.get("event_id")
    conn = get_db_connection()
    if event_id is None:
        event_id = get_active_event_id(conn)
    else:
        row = conn.execute("SELECT id FROM events WHERE id = ?", (event_id,)).fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "event not found"}), 404
    if not event_id:
        conn.close()
        return jsonify({"error": "no event"}), 400
    deleted = purge_orders_for_event(conn, event_id)
    conn.close()
    return jsonify({"status": "ok", "event_id": event_id, "deleted_orders": deleted})


@admin_bp.route("/admin/events/stats")
def event_stats():
    event_id = request.args.get("event_id", type=int)
    conn = get_db_connection()

    if event_id is None:
        active = conn.execute("""
            SELECT id
            FROM events
            WHERE status = 'active'
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()
        event_id = active["id"] if active else None

    if event_id is None:
        conn.close()
        return jsonify({"error": "no event"}), 400

    summary = conn.execute("""
        WITH order_totals AS (
            SELECT
                o.id AS order_id,
                o.order_number,
                o.table_id,
                o.waiter_id,
                o.status,
                COALESCE(SUM(oi.quantity_total * COALESCE(oi.unit_price, p.price)), 0) AS total_amount,
                COALESCE(SUM(oi.quantity_open * COALESCE(oi.unit_price, p.price)), 0) AS open_amount
            FROM orders o
            LEFT JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN products p ON p.id = oi.product_id
            WHERE o.event_id = ?
            GROUP BY o.id, o.order_number, o.table_id, o.waiter_id, o.status
        )
        SELECT
            COUNT(*) AS orders_total,
            SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS orders_paid,
            SUM(CASE WHEN status != 'paid' THEN 1 ELSE 0 END) AS orders_open,
            COALESCE(SUM(total_amount), 0) AS orders_total_amount,
            COALESCE(SUM(open_amount), 0) AS orders_open_amount
        FROM order_totals
    """, (event_id,)).fetchone()

    payments_sum = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN payment_type = 'paid' THEN amount ELSE 0 END), 0) AS paid_amount,
            COALESCE(SUM(CASE WHEN payment_type = 'internal' THEN 1 ELSE 0 END), 0) AS internal_bookings,
            COUNT(*) AS payments_count
        FROM payments
        WHERE order_id IN (SELECT id FROM orders WHERE event_id = ?)
    """, (event_id,)).fetchone()

    tab_cash = conn.execute("""
        SELECT COALESCE(SUM(tp.amount), 0) AS tab_paid_amount
        FROM tab_payments tp
        JOIN tabs t ON t.id = tp.tab_id
        WHERE t.event_id = ?
          AND t.active = 1
    """, (event_id,)).fetchone()

    open_amount = conn.execute("""
        SELECT COALESCE(SUM(oi.quantity_open * COALESCE(oi.unit_price, p.price)), 0) AS open_amount
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.event_id = ?
    """, (event_id,)).fetchone()

    by_product = conn.execute("""
        SELECT
            COALESCE(oi.product_name, p.name) AS name,
            SUM(oi.quantity_paid) AS qty_paid,
            SUM(oi.quantity_open) AS qty_open,
            SUM(oi.quantity_total) AS qty_total,
            SUM(oi.quantity_paid * COALESCE(oi.unit_price, p.price)) AS revenue
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.event_id = ?
        GROUP BY COALESCE(oi.product_name, p.name)
        ORDER BY revenue DESC
        LIMIT 200
    """, (event_id,)).fetchall()

    by_waiter = conn.execute("""
        WITH order_totals AS (
            SELECT
                o.id,
                o.waiter_id,
                COALESCE(SUM(oi.quantity_total * COALESCE(oi.unit_price, p.price)), 0) AS total_amount,
                COALESCE(SUM(oi.quantity_open * COALESCE(oi.unit_price, p.price)), 0) AS open_amount
            FROM orders o
            LEFT JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN products p ON p.id = oi.product_id
            WHERE o.event_id = ?
            GROUP BY o.id, o.waiter_id
        )
        SELECT
            COALESCE(u.name, 'Unbekannt') AS waiter_name,
            COUNT(*) AS orders,
            COALESCE(SUM(ot.total_amount), 0) AS orders_total_amount,
            COALESCE(SUM(ot.open_amount), 0) AS orders_open_amount
        FROM order_totals ot
        LEFT JOIN users u ON u.id = ot.waiter_id
        GROUP BY ot.waiter_id
        ORDER BY orders_total_amount DESC
        LIMIT 200
    """, (event_id,)).fetchall()

    by_table = conn.execute("""
        WITH order_totals AS (
            SELECT
                o.id,
                o.table_id,
                COALESCE(SUM(oi.quantity_total * COALESCE(oi.unit_price, p.price)), 0) AS total_amount,
                COALESCE(SUM(oi.quantity_open * COALESCE(oi.unit_price, p.price)), 0) AS open_amount
            FROM orders o
            LEFT JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN products p ON p.id = oi.product_id
            WHERE o.event_id = ?
            GROUP BY o.id, o.table_id
        )
        SELECT
            COALESCE(t.name, 'Theke') AS table_name,
            COUNT(*) AS orders,
            COALESCE(SUM(ot.total_amount), 0) AS orders_total_amount,
            COALESCE(SUM(ot.open_amount), 0) AS orders_open_amount
        FROM order_totals ot
        LEFT JOIN tables t ON t.id = ot.table_id
        GROUP BY ot.table_id
        ORDER BY orders_total_amount DESC
        LIMIT 300
    """, (event_id,)).fetchall()

    by_category = conn.execute("""
        SELECT
            COALESCE(c.name, 'Ohne Kategorie') AS category_name,
            COALESCE(SUM(oi.quantity_total * COALESCE(oi.unit_price, p.price)), 0) AS total_amount,
            COALESCE(SUM(oi.quantity_open * COALESCE(oi.unit_price, p.price)), 0) AS open_amount
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE o.event_id = ?
        GROUP BY COALESCE(c.name, 'Ohne Kategorie')
        ORDER BY total_amount DESC
        LIMIT 300
    """, (event_id,)).fetchall()

    orders_list = conn.execute("""
        SELECT
            o.id,
            o.order_number,
            COALESCE(u.name, 'Unbekannt') AS waiter_name,
            COALESCE(t.name, 'Theke') AS table_name,
            o.status,
            COALESCE(SUM(oi.quantity_total * COALESCE(oi.unit_price, p.price)), 0) AS total_amount,
            COALESCE(SUM(oi.quantity_open * COALESCE(oi.unit_price, p.price)), 0) AS open_amount
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        LEFT JOIN products p ON p.id = oi.product_id
        LEFT JOIN users u ON u.id = o.waiter_id
        LEFT JOIN tables t ON t.id = o.table_id
        WHERE o.event_id = ?
        GROUP BY o.id, o.order_number, u.name, t.name, o.status
        ORDER BY o.order_number ASC
        LIMIT 2000
    """, (event_id,)).fetchall()

    by_station_product = conn.execute("""
        SELECT
            us.name AS station_name,
            COALESCE(oi.product_name, p.name) AS product_name,
            SUM(CASE WHEN pay.payment_type='internal' THEN pi.quantity ELSE 0 END) AS qty_internal,
            SUM(CASE WHEN pay.payment_type='paid' THEN pi.quantity ELSE 0 END) AS qty_paid,
            SUM(CASE WHEN pay.payment_type='paid' THEN pi.quantity * COALESCE(oi.unit_price, p.price) ELSE 0 END) AS revenue_paid
        FROM payment_items pi
        JOIN payments pay ON pay.id = pi.payment_id
        JOIN order_items oi ON oi.id = pi.order_item_id
        JOIN orders o ON o.id = oi.order_id
        LEFT JOIN users us ON us.id = o.source_station_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.event_id = ?
        GROUP BY us.name, COALESCE(oi.product_name, p.name)
        ORDER BY station_name ASC, qty_internal DESC, revenue_paid DESC
        LIMIT 300
    """, (event_id,)).fetchall()

    tab_bal = sql_tab_open_balance("t")
    tab_rows_raw = conn.execute(f"""
        SELECT
            t.id,
            t.name,
            {tab_bal} AS balance,
            COALESCE((SELECT SUM(te.amount) FROM tab_entries te WHERE te.tab_id = t.id), 0) AS entries_amount,
            COALESCE((SELECT SUM(tp.amount) FROM tab_payments tp WHERE tp.tab_id = t.id), 0) AS payments_amount
        FROM tabs t
        WHERE t.event_id = ?
          AND t.active = 1
        ORDER BY t.name COLLATE NOCASE ASC
        LIMIT 300
    """, (event_id,)).fetchall()

    tab_rows = []
    for r in tab_rows_raw:
        d = dict(r)
        d["balance"] = max(0.0, float(d.get("balance") or 0))
        tab_rows.append(d)
    open_tabs_amount = sum(float((r["balance"] or 0)) for r in tab_rows)
    open_total_amount = float(summary["orders_open_amount"] or 0) + open_tabs_amount
    revenue_total_amount = float(summary["orders_total_amount"] or 0)
    final_total = float(payments_sum["paid_amount"] or 0) + float(tab_cash["tab_paid_amount"] or 0)

    conn.close()
    return jsonify({
        "event_id": event_id,
        "summary": dict(summary),
        "paid": dict(payments_sum),
        "tab_cash": dict(tab_cash),
        "open": dict(open_amount),
        "open_total_amount": open_total_amount,
        "revenue_total_amount": revenue_total_amount,
        "final_total": final_total,
        "orders": [dict(r) for r in orders_list],
        "by_product": [dict(r) for r in by_product],
        "by_waiter": [dict(r) for r in by_waiter],
        "by_table": [dict(r) for r in by_table],
        "by_category": [dict(r) for r in by_category],
        "by_station_product": [dict(r) for r in by_station_product],
        "tabs": [dict(r) for r in tab_rows],
    })


@admin_bp.route("/admin/tabs", methods=["GET", "POST"])
def admin_tabs():
    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    if request.method == "POST":
        data = request.json or {}
        name = (data.get("name") or "").strip()
        if not name:
            conn.close()
            return jsonify({"error": "name required"}), 400
        cur = conn.execute("""
            INSERT INTO tabs (event_id, name, active)
            VALUES (?, ?, 1)
        """, (event_id, name))
        conn.commit()
        tab_id = cur.lastrowid
        conn.close()
        return jsonify({"status": "ok", "tab_id": tab_id})

    tab_bal = sql_tab_open_balance("t")
    rows = conn.execute(f"""
        SELECT
            t.id,
            t.name,
            {tab_bal} AS balance
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
    conn.close()
    return jsonify(out)

# ============================================================
# [1000] CATEGORIES
# ============================================================
@admin_bp.route("/admin/categories", methods=["GET", "POST"])
def categories():
    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    if request.method == "POST":
        data = request.json
        conn.execute("INSERT INTO categories (event_id, name) VALUES (?, ?)", (event_id, data["name"]))
        conn.commit()

    rows = conn.execute("""
        SELECT *
        FROM categories
        WHERE event_id = ?
        ORDER BY id ASC
    """, (event_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ============================================================
# [1010] DELETE CATEGORY
# ============================================================
@admin_bp.route("/admin/categories/delete", methods=["POST"])
def delete_category():
    conn = get_db_connection()
    data = request.json

    conn.execute("DELETE FROM categories WHERE id = ?", (data["id"],))
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

# ============================================================
# [1100] PRODUCTS
# ============================================================
@admin_bp.route("/admin/products", methods=["GET", "POST"])
def products():
    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    if request.method == "POST":
        data = request.json
        conn.execute("""
            INSERT INTO products (event_id, name, price, category_id)
            VALUES (?, ?, ?, ?)
        """, (event_id, data["name"], data["price"], data["category_id"]))
        conn.commit()

    rows = conn.execute("""
        SELECT p.id, p.name, p.price, c.name as category, p.category_id
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.event_id = ?
        ORDER BY p.id ASC
    """, (event_id,)).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])

# ============================================================
# [1110] DELETE PRODUCT
# ============================================================
@admin_bp.route("/admin/products/delete", methods=["POST"])
def delete_product():
    conn = get_db_connection()
    data = request.json

    conn.execute("DELETE FROM products WHERE id = ?", (data["id"],))
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

# ============================================================
# [1120] UPDATE PRODUCT
# ============================================================
@admin_bp.route("/admin/products/update", methods=["POST"])
def update_product():
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    data = request.json

    conn.execute("""
        UPDATE products
        SET name = ?, price = ?, category_id = ?
        WHERE id = ? AND event_id = ?
    """, (data["name"], data["price"], data["category_id"], data["id"], event_id))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# ============================================================
# [1200] USERS + TABLES + ASSIGNMENTS + STATION CATEGORIES
# ============================================================
@admin_bp.route("/admin/users", methods=["GET", "POST"])
def users():
    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    if request.method == "POST":
        data = request.json
        conn.execute("""
            INSERT INTO users (event_id, name, pin, role, active)
            VALUES (?, ?, ?, ?, 1)
        """, (event_id, data["name"], data["pin"], data["role"]))
        conn.commit()

    users_rows = conn.execute("""
        SELECT id, name, pin, role, active
        FROM users
        WHERE event_id = ?
        ORDER BY id ASC
    """, (event_id,)).fetchall()

    tables_rows = conn.execute("""
        SELECT id, name
        FROM tables
        WHERE event_id = ?
        ORDER BY id ASC
    """, (event_id,)).fetchall()

    assignment_rows = conn.execute("""
        SELECT waiter_id, table_id
        FROM waiter_tables
        WHERE event_id = ?
        ORDER BY waiter_id, table_id
    """, (event_id,)).fetchall()

    station_category_rows = conn.execute("""
        SELECT station_id, category_id
        FROM station_categories
        WHERE event_id = ?
        ORDER BY station_id, category_id
    """, (event_id,)).fetchall()

    conn.close()

    return jsonify({
        "users": [dict(u) for u in users_rows],
        "tables": [dict(t) for t in tables_rows],
        "assignments": [dict(a) for a in assignment_rows],
        "station_categories": [dict(sc) for sc in station_category_rows]
    })

# ============================================================
# [1210] DELETE USER
# ============================================================
@admin_bp.route("/admin/users/delete", methods=["POST"])
def delete_user():
    conn = get_db_connection()
    data = request.json

    conn.execute("DELETE FROM users WHERE id = ?", (data["id"],))
    conn.execute("DELETE FROM waiter_tables WHERE waiter_id = ?", (data["id"],))
    conn.execute("DELETE FROM station_categories WHERE station_id = ?", (data["id"],))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

# ============================================================
# [1220] UPDATE USER TABLE ASSIGNMENTS
# ============================================================
@admin_bp.route("/admin/users/assign", methods=["POST"])
def assign_tables():
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    data = request.json

    user_id = data["user_id"]
    table_ids = data["table_ids"]

    conn.execute("DELETE FROM waiter_tables WHERE waiter_id = ? AND event_id = ?", (user_id, event_id))

    for t in table_ids:
        conn.execute("""
            INSERT INTO waiter_tables (event_id, waiter_id, table_id)
            VALUES (?, ?, ?)
        """, (event_id, user_id, t))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

# ============================================================
# [1230] UPDATE STATION CATEGORY ASSIGNMENTS
# ============================================================
@admin_bp.route("/admin/station/categories", methods=["POST"])
def assign_station_categories():
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    data = request.json

    station_id = data["station_id"]
    category_ids = data["category_ids"]

    conn.execute("DELETE FROM station_categories WHERE station_id = ? AND event_id = ?", (station_id, event_id))

    for cid in category_ids:
        conn.execute("""
            INSERT INTO station_categories (event_id, station_id, category_id)
            VALUES (?, ?, ?)
        """, (event_id, station_id, cid))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

# ============================================================
# [1300] TABLES
# ============================================================
@admin_bp.route("/admin/tables", methods=["GET", "POST"])
def tables():
    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    if request.method == "POST":
        data = request.json
        conn.execute("INSERT INTO tables (event_id, name) VALUES (?, ?)", (event_id, data["name"]))
        conn.commit()

    rows = conn.execute("""
        SELECT id, name
        FROM tables
        WHERE event_id = ?
        ORDER BY id ASC
    """, (event_id,)).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])

# ============================================================
# [1310] DELETE TABLE
# ============================================================
@admin_bp.route("/admin/tables/delete", methods=["POST"])
def delete_table():
    conn = get_db_connection()
    data = request.json

    conn.execute("DELETE FROM tables WHERE id = ?", (data["id"],))
    conn.execute("DELETE FROM waiter_tables WHERE table_id = ?", (data["id"],))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})
