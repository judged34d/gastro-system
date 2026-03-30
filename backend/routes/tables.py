from flask import Blueprint, jsonify
from db import get_db_connection, get_active_event_id

tables_bp = Blueprint('tables', __name__)

@tables_bp.route("/waiter/<int:waiter_id>/tables")
def get_waiter_tables(waiter_id):

    conn = get_db_connection()
    event_id = get_active_event_id(conn)

    rows = conn.execute("""
        SELECT t.id, t.name
        FROM tables t
        JOIN waiter_tables wt ON wt.table_id = t.id
        WHERE wt.waiter_id = ?
          AND t.event_id = ?
          AND wt.event_id = ?
    """, (waiter_id, event_id, event_id)).fetchall()

    conn.close()

    return jsonify([dict(r) for r in rows])
