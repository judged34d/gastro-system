from flask import Blueprint, jsonify, request
from db import get_db_connection, get_active_event_id

tables_bp = Blueprint("tables", __name__)


@tables_bp.route("/public/table/<int:table_id>")
def public_table(table_id):
    """Öffentliche Tisch-Info für QR-Gastbestellung (nur aktives Event)."""
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    row = conn.execute(
        """
        SELECT id, name
        FROM tables
        WHERE id = ?
          AND event_id = ?
        """,
        (table_id, event_id),
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify({"id": row["id"], "name": row["name"]})


@tables_bp.route("/waiter/<int:waiter_id>/tables")
def get_waiter_tables(waiter_id):
    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    rows = conn.execute(
        """
        SELECT t.id, t.name
        FROM tables t
        JOIN waiter_tables wt ON wt.table_id = t.id
        WHERE wt.waiter_id = ?
          AND t.event_id = ?
          AND wt.event_id = ?
        """,
        (waiter_id, event_id, event_id),
    ).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])


def _open_order_rows(conn, event_id, *, waiter_id=None, exclude_waiter_id=None):
    """Offene Orders mit Positionen; optional nur eigene oder alle außer eigener."""
    sql = """
        SELECT
            o.id AS order_id,
            o.order_number,
            o.table_id,
            o.waiter_id,
            o.created_at,
            t.name AS table_name,
            u.name AS waiter_name
        FROM orders o
        JOIN tables t ON t.id = o.table_id
        LEFT JOIN users u ON u.id = o.waiter_id
        WHERE o.event_id = ?
          AND t.event_id = ?
          AND o.status != 'paid'
          AND EXISTS (
              SELECT 1 FROM order_items oi
              WHERE oi.order_id = o.id AND oi.quantity_open > 0
          )
    """
    params: list = [event_id, event_id]
    if waiter_id is not None:
        sql += " AND o.waiter_id = ?"
        params.append(waiter_id)
    if exclude_waiter_id is not None:
        sql += " AND (o.waiter_id IS NULL OR o.waiter_id != ?)"
        params.append(exclude_waiter_id)
    sql += " ORDER BY o.created_at ASC"

    orders = conn.execute(sql, params).fetchall()
    result = []
    for o in orders:
        items = conn.execute(
            """
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
            """,
            (o["order_id"],),
        ).fetchall()
        result.append(
            {
                "order_id": o["order_id"],
                "order_number": o["order_number"],
                "table_id": o["table_id"],
                "table_name": o["table_name"],
                "waiter_id": o["waiter_id"],
                "waiter_name": o["waiter_name"] or ("Gast/QR" if o["waiter_id"] is None else "—"),
                "created_at": o["created_at"],
                "items": [dict(i) for i in items],
            }
        )
    return result


@tables_bp.route("/waiter/<int:waiter_id>/orders/open-count")
def waiter_open_orders_count(waiter_id):
    """Anzahl eigener offener Bestellungen (waiter_id), nicht aller Tisch-Orders."""
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT o.id) AS cnt
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id AND oi.quantity_open > 0
        WHERE o.waiter_id = ?
          AND o.event_id = ?
          AND o.status != 'paid'
        """,
        (waiter_id, event_id),
    ).fetchone()
    conn.close()
    return jsonify({"count": int(row["cnt"] or 0) if row else 0})


@tables_bp.route("/waiter/<int:waiter_id>/orders/mine")
def waiter_orders_mine(waiter_id):
    """Offene Bestellungen der Bedienung (Meine Aufgabe)."""
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    result = _open_order_rows(conn, event_id, waiter_id=waiter_id)
    conn.close()
    return jsonify(result)


@tables_bp.route("/waiter/<int:waiter_id>/orders/colleagues")
def waiter_orders_colleagues(waiter_id):
    """Alle offenen Bestellungen anderer (alle Tische) — Einsicht zum Einspringen."""
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    result = _open_order_rows(conn, event_id, exclude_waiter_id=waiter_id)
    conn.close()
    return jsonify(result)


def _claim_row_dict(conn, row) -> dict:
    items = conn.execute(
        """
        SELECT
            COALESCE(oi.product_name, p.name) AS name,
            oi.quantity_open
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ? AND oi.quantity_open > 0
        """,
        (row["order_id"],),
    ).fetchall()
    return {
        "id": row["id"],
        "order_id": row["order_id"],
        "order_number": row["order_number"],
        "table_id": row["table_id"],
        "table_name": row["table_name"],
        "from_waiter_id": row["from_waiter_id"],
        "from_waiter_name": row["from_waiter_name"],
        "to_waiter_id": row["to_waiter_id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "items_preview": [
            f'{i["quantity_open"]}× {i["name"]}' for i in items
        ],
    }


@tables_bp.route("/waiter/<int:waiter_id>/claim-requests/incoming")
def claim_requests_incoming(waiter_id):
    """Offene Übernahme-Anfragen an mich."""
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    rows = conn.execute(
        """
        SELECT
            r.id,
            r.order_id,
            r.from_waiter_id,
            r.to_waiter_id,
            r.status,
            r.created_at,
            o.order_number,
            o.table_id,
            t.name AS table_name,
            u.name AS from_waiter_name
        FROM order_claim_requests r
        JOIN orders o ON o.id = r.order_id
        JOIN tables t ON t.id = o.table_id
        JOIN users u ON u.id = r.from_waiter_id
        WHERE r.to_waiter_id = ?
          AND r.event_id = ?
          AND r.status = 'pending'
          AND o.status != 'paid'
        ORDER BY r.created_at ASC
        """,
        (waiter_id, event_id),
    ).fetchall()
    out = [_claim_row_dict(conn, r) for r in rows]
    conn.close()
    return jsonify(out)


@tables_bp.route("/waiter/<int:waiter_id>/claim-requests/incoming-count")
def claim_requests_incoming_count(waiter_id):
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM order_claim_requests r
        JOIN orders o ON o.id = r.order_id
        WHERE r.to_waiter_id = ?
          AND r.event_id = ?
          AND r.status = 'pending'
          AND o.status != 'paid'
        """,
        (waiter_id, event_id),
    ).fetchone()
    conn.close()
    return jsonify({"count": int(row["cnt"] or 0) if row else 0})


@tables_bp.route("/waiter/<int:waiter_id>/orders/<int:order_id>/claim-request", methods=["POST"])
def create_claim_request(waiter_id, order_id):
    """Übernahme anfragen (bei Gast/QR ohne Owner: direkt übernehmen)."""
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    order = conn.execute(
        """
        SELECT id, waiter_id, status, event_id
        FROM orders
        WHERE id = ? AND event_id = ?
        """,
        (order_id, event_id),
    ).fetchone()
    if not order:
        conn.close()
        return jsonify({"error": "Bestellung nicht gefunden"}), 404
    if order["status"] == "paid":
        conn.close()
        return jsonify({"error": "Bestellung bereits bezahlt"}), 400
    if order["waiter_id"] == waiter_id:
        conn.close()
        return jsonify({"error": "Bestellung gehört bereits dir"}), 400

    # Gast/QR ohne Bedienung: sofort zuweisen
    if order["waiter_id"] is None:
        conn.execute(
            "UPDATE orders SET waiter_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (waiter_id, order_id),
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "mode": "direct", "order_id": order_id})

    existing = conn.execute(
        """
        SELECT id FROM order_claim_requests
        WHERE order_id = ?
          AND from_waiter_id = ?
          AND status = 'pending'
        """,
        (order_id, waiter_id),
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"ok": True, "mode": "pending", "id": existing["id"]})

    cur = conn.execute(
        """
        INSERT INTO order_claim_requests
            (event_id, order_id, from_waiter_id, to_waiter_id, status)
        VALUES (?, ?, ?, ?, 'pending')
        """,
        (event_id, order_id, waiter_id, order["waiter_id"]),
    )
    conn.commit()
    req_id = cur.lastrowid
    conn.close()
    return jsonify({"ok": True, "mode": "pending", "id": req_id})


@tables_bp.route(
    "/waiter/<int:waiter_id>/claim-requests/<int:request_id>/accept",
    methods=["POST"],
)
def accept_claim_request(waiter_id, request_id):
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    row = conn.execute(
        """
        SELECT id, order_id, from_waiter_id, to_waiter_id, status
        FROM order_claim_requests
        WHERE id = ? AND event_id = ?
        """,
        (request_id, event_id),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Anfrage nicht gefunden"}), 404
    if row["to_waiter_id"] != waiter_id:
        conn.close()
        return jsonify({"error": "Keine Berechtigung"}), 403
    if row["status"] != "pending":
        conn.close()
        return jsonify({"error": "Anfrage nicht mehr offen"}), 400

    order = conn.execute(
        "SELECT id, waiter_id, status FROM orders WHERE id = ?",
        (row["order_id"],),
    ).fetchone()
    if not order or order["status"] == "paid":
        conn.execute(
            """
            UPDATE order_claim_requests
            SET status = 'cancelled', resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (request_id,),
        )
        conn.commit()
        conn.close()
        return jsonify({"error": "Bestellung nicht mehr übernehmbar"}), 400

    conn.execute(
        "UPDATE orders SET waiter_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (row["from_waiter_id"], row["order_id"]),
    )
    conn.execute(
        """
        UPDATE order_claim_requests
        SET status = 'accepted', resolved_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (request_id,),
    )
    # andere offene Anfragen zu derselben Order verwerfen
    conn.execute(
        """
        UPDATE order_claim_requests
        SET status = 'cancelled', resolved_at = CURRENT_TIMESTAMP
        WHERE order_id = ? AND status = 'pending' AND id != ?
        """,
        (row["order_id"], request_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "order_id": row["order_id"]})


@tables_bp.route(
    "/waiter/<int:waiter_id>/claim-requests/<int:request_id>/reject",
    methods=["POST"],
)
def reject_claim_request(waiter_id, request_id):
    conn = get_db_connection()
    event_id = get_active_event_id(conn)
    row = conn.execute(
        """
        SELECT id, to_waiter_id, status
        FROM order_claim_requests
        WHERE id = ? AND event_id = ?
        """,
        (request_id, event_id),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Anfrage nicht gefunden"}), 404
    if row["to_waiter_id"] != waiter_id:
        conn.close()
        return jsonify({"error": "Keine Berechtigung"}), 403
    if row["status"] != "pending":
        conn.close()
        return jsonify({"error": "Anfrage nicht mehr offen"}), 400

    conn.execute(
        """
        UPDATE order_claim_requests
        SET status = 'rejected', resolved_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (request_id,),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})
