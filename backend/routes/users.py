from flask import Blueprint, jsonify
from db import get_db_connection

users_bp = Blueprint('users', __name__)

@users_bp.route("/users")
def get_users():
    conn = get_db_connection()

    users = conn.execute("""
        SELECT id, name, role, pin
        FROM users
        WHERE active = 1
    """).fetchall()

    conn.close()

    return jsonify([dict(u) for u in users])
