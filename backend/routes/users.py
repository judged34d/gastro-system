from flask import Blueprint, jsonify
from db import get_db_connection, get_active_event_id

users_bp = Blueprint('users', __name__)

@users_bp.route("/users")
def get_users():
    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    users = conn.execute("""
        SELECT id, name, role, pin
        FROM users
        WHERE active = 1
          AND event_id = ?
    """, (event_id,)).fetchall()

    conn.close()

    return jsonify([dict(u) for u in users])
