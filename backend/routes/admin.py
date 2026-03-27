from flask import Blueprint, request, jsonify
from db import get_db_connection

admin_bp = Blueprint('admin', __name__)

# ============================================================
# [1000] CATEGORIES
# ============================================================
@admin_bp.route("/admin/categories", methods=["GET", "POST"])
def categories():
    conn = get_db_connection()

    if request.method == "POST":
        data = request.json
        conn.execute("INSERT INTO categories (name) VALUES (?)", (data["name"],))
        conn.commit()

    rows = conn.execute("SELECT * FROM categories ORDER BY id ASC").fetchall()
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

    if request.method == "POST":
        data = request.json
        conn.execute("""
            INSERT INTO products (name, price, category_id)
            VALUES (?, ?, ?)
        """, (data["name"], data["price"], data["category_id"]))
        conn.commit()

    rows = conn.execute("""
        SELECT p.id, p.name, p.price, c.name as category, p.category_id
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        ORDER BY p.id ASC
    """).fetchall()

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
    data = request.json

    conn.execute("""
        UPDATE products
        SET name = ?, price = ?, category_id = ?
        WHERE id = ?
    """, (data["name"], data["price"], data["category_id"], data["id"]))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# ============================================================
# [1200] USERS + TABLES + ASSIGNMENTS + STATION CATEGORIES
# ============================================================
@admin_bp.route("/admin/users", methods=["GET", "POST"])
def users():
    conn = get_db_connection()

    if request.method == "POST":
        data = request.json
        conn.execute("""
            INSERT INTO users (name, pin, role, active)
            VALUES (?, ?, ?, 1)
        """, (data["name"], data["pin"], data["role"]))
        conn.commit()

    users_rows = conn.execute("""
        SELECT id, name, pin, role, active
        FROM users
        ORDER BY id ASC
    """).fetchall()

    tables_rows = conn.execute("""
        SELECT id, name
        FROM tables
        ORDER BY id ASC
    """).fetchall()

    assignment_rows = conn.execute("""
        SELECT waiter_id, table_id
        FROM waiter_tables
        ORDER BY waiter_id, table_id
    """).fetchall()

    station_category_rows = conn.execute("""
        SELECT station_id, category_id
        FROM station_categories
        ORDER BY station_id, category_id
    """).fetchall()

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
    data = request.json

    user_id = data["user_id"]
    table_ids = data["table_ids"]

    conn.execute("DELETE FROM waiter_tables WHERE waiter_id = ?", (user_id,))

    for t in table_ids:
        conn.execute("""
            INSERT INTO waiter_tables (waiter_id, table_id)
            VALUES (?, ?)
        """, (user_id, t))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

# ============================================================
# [1230] UPDATE STATION CATEGORY ASSIGNMENTS
# ============================================================
@admin_bp.route("/admin/station/categories", methods=["POST"])
def assign_station_categories():
    conn = get_db_connection()
    data = request.json

    station_id = data["station_id"]
    category_ids = data["category_ids"]

    conn.execute("DELETE FROM station_categories WHERE station_id = ?", (station_id,))

    for cid in category_ids:
        conn.execute("""
            INSERT INTO station_categories (station_id, category_id)
            VALUES (?, ?)
        """, (station_id, cid))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

# ============================================================
# [1300] TABLES
# ============================================================
@admin_bp.route("/admin/tables", methods=["GET", "POST"])
def tables():
    conn = get_db_connection()

    if request.method == "POST":
        data = request.json
        conn.execute("INSERT INTO tables (name) VALUES (?)", (data["name"],))
        conn.commit()

    rows = conn.execute("""
        SELECT id, name
        FROM tables
        ORDER BY id ASC
    """).fetchall()

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
