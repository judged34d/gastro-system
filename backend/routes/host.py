"""Host-only API (Control Panel). Destructive DB ops require GASTRO_HOST_TOKEN."""

import os

from flask import Blueprint, jsonify, request

from db import get_active_event_id, get_db_connection, purge_database_for_live, purge_orders_for_event, purge_event_completely

host_bp = Blueprint("host", __name__)


def _host_token_ok() -> bool:
    expected = (os.environ.get("GASTRO_HOST_TOKEN") or "").strip()
    if not expected:
        return False
    got = (request.headers.get("X-Gastro-Host-Token") or "").strip()
    if not got and request.headers.get("Authorization", "").startswith("Bearer "):
        got = request.headers.get("Authorization", "")[7:].strip()
    return got == expected


def _require_host():
    if not _host_token_ok():
        return jsonify({"error": "host token required", "hint": "Nur GastroSystem Control Panel"}), 403
    return None


@host_bp.route("/host/events", methods=["GET"])
def host_list_events():
    err = _require_host()
    if err:
        return err
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT id, name, status, starts_at, ends_at
        FROM events
        ORDER BY id DESC
        """
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@host_bp.route("/host/events/clear-orders", methods=["POST"])
def host_clear_event_orders():
    """
  Control Panel only:
  - live_reset: wipe all events + master data, new empty active event
  - else: purge all orders for event_id (or active event)
    """
    err = _require_host()
    if err:
        return err
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


@host_bp.route("/host/events/delete", methods=["POST"])
def host_delete_event():
    """Delete one closed event including all data (host token required)."""
    err = _require_host()
    if err:
        return err
    data = request.json or {}
    event_id = data.get("event_id")
    if not event_id:
        return jsonify({"error": "event_id required"}), 400
    conn = get_db_connection()
    ev = conn.execute(
        "SELECT id, status FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if not ev:
        conn.close()
        return jsonify({"error": "not found"}), 404
    if ev["status"] == "active":
        conn.close()
        return jsonify({"error": "cannot delete active event"}), 400
    result = purge_event_completely(conn, event_id)
    conn.close()
    if not result:
        return jsonify({"error": "delete failed"}), 500
    return jsonify({"status": "ok", **result})
