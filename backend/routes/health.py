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
