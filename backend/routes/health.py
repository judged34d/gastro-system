from flask import Blueprint, jsonify

from db import get_db_connection

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return jsonify({"ok": True, "db": True})
    except Exception as e:
        return jsonify({"ok": False, "db": False, "error": str(e)}), 503


@health_bp.route("/event/active")
def active_event_context():
    """Leichtgewichtiger Kontext fürs Frontend (Demo-Banner)."""
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT id, name, status, COALESCE(is_demo, 0) AS is_demo
        FROM events
        WHERE status = 'active'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"active": False})
    return jsonify(
        {
            "active": True,
            "event_id": int(row["id"]),
            "event_name": row["name"],
            "is_demo": bool(int(row["is_demo"] or 0)),
        }
    )
