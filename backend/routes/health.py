import json

from flask import Blueprint, Response, jsonify, request, stream_with_context

from activity import fetch_activity, latest_activity_id, wait_activity_events
from db import get_db_connection

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        activity_latest_id = 0
        try:
            latest = conn.execute(
                "SELECT MAX(id) AS mid FROM activity_log"
            ).fetchone()
            activity_latest_id = int(latest["mid"] or 0) if latest else 0
        except Exception:
            activity_latest_id = latest_activity_id()
        conn.close()
        return jsonify(
            {
                "ok": True,
                "db": True,
                "activity_latest_id": max(activity_latest_id, latest_activity_id()),
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "db": False, "error": str(e)}), 503


@health_bp.route("/activity/live")
def activity_live():
    """Snapshot (Fallback); bevorzugt /activity/stream fuer Echtzeit."""
    since_id = request.args.get("since_id", default=0, type=int) or 0
    limit = request.args.get("limit", default=80, type=int) or 80
    conn = get_db_connection()
    events = fetch_activity(conn, since_id=since_id, limit=limit)
    latest = conn.execute("SELECT MAX(id) AS mid FROM activity_log").fetchone()
    conn.close()
    return jsonify(
        {
            "events": events,
            "latest_id": int(latest["mid"] or 0) if latest else 0,
        }
    )


@health_bp.route("/activity/stream")
def activity_stream():
    """
    Server-Sent Events: neue Aktivitaeten werden sofort gepusht
    (kein Client-Polling im Sekunden-Takt).
    """
    since_id = request.args.get("since_id", default=0, type=int) or 0

    @stream_with_context
    def generate():
        last_id = max(0, int(since_id or 0))
        # Kurzer DB-Backlog nach Connect / Reconnect
        try:
            conn = get_db_connection()
            backlog = fetch_activity(conn, since_id=last_id, limit=80)
            conn.close()
            for ev in backlog:
                last_id = max(last_id, int(ev.get("id") or 0))
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

        yield ": connected\n\n"

        while True:
            events = wait_activity_events(last_id, timeout=15.0)
            if not events:
                yield ": keepalive\n\n"
                continue
            for ev in events:
                eid = int(ev.get("id") or 0)
                if eid <= last_id:
                    continue
                last_id = eid
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers=headers,
    )


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
