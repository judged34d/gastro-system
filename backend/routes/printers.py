from flask import Blueprint, jsonify, request

from db import get_db_connection, get_active_event_id
from printer import (
    build_station_ticket,
    build_station_ticket_payload,
    build_test_ticket,
    list_windows_printers,
    load_printer_config,
    print_station_order,
    save_printer_config,
    send_to_printer,
    station_printer_cfg,
)

printers_bp = Blueprint("printers", __name__)


@printers_bp.route("/admin/printers", methods=["GET", "POST"])
def admin_printers():
    conn = get_db_connection()
    if request.method == "POST":
        data = request.json or {}
        save_printer_config(conn, data)
        conn.commit()
    cfg = load_printer_config(conn)
    event_id = get_active_event_id(conn)
    stations = conn.execute(
        """
        SELECT id, name
        FROM users
        WHERE role = 'station'
          AND event_id = ?
        ORDER BY name ASC
        """,
        (event_id,),
    ).fetchall()
    conn.close()
    return jsonify(
        {
            "autoprint": bool(cfg.get("autoprint")),
            "stations_config": cfg.get("stations") or {},
            "stations": [dict(s) for s in stations],
            "windows_printers": list_windows_printers(),
        }
    )


@printers_bp.route("/admin/printers/windows")
def admin_windows_printers():
    return jsonify({"printers": list_windows_printers()})


@printers_bp.route("/admin/printers/test", methods=["POST"])
def admin_printer_test():
    data = request.json or {}
    try:
        station_id = int(data.get("station_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "station_id required"}), 400

    conn = get_db_connection()
    cfg = station_printer_cfg(conn, station_id)
    override = data.get("config")
    if isinstance(override, dict):
        conn_type = str(override.get("connection") or "cups").strip().lower()
        if conn_type in ("ipp", "cups/ipp", "cups_ipp"):
            conn_type = "cups"
        cfg = {
            "enabled": True,
            "connection": conn_type,
            "host": str(override.get("host") or "").strip(),
            "port": int(override.get("port") or (631 if conn_type == "cups" else 9100)),
            "queue_name": str(override.get("queue_name") or "").strip(),
            "cups_user": str(override.get("cups_user") or "").strip(),
            "cups_password": str(override.get("cups_password") or ""),
            "windows_name": str(override.get("windows_name") or "").strip(),
            "agent_url": str(override.get("agent_url") or "").strip(),
            "copies": 1,
        }
    if not cfg:
        conn.close()
        return jsonify({"error": "Drucker für Station nicht aktiv / nicht konfiguriert"}), 400

    station = conn.execute(
        "SELECT name FROM users WHERE id = ? AND role = 'station'",
        (station_id,),
    ).fetchone()
    conn.close()
    name = station["name"] if station else f"Station {station_id}"
    conn_type = str(cfg.get("connection") or "").lower()
    if conn_type in ("browser", "client") or (
        conn_type in ("agent", "station_agent", "local", "terminal")
        and not (cfg.get("agent_url") or "").strip()
    ):
        return jsonify(
            {
                "ok": True,
                "mode": "client_browser",
                "hint": "Browser-Druck: Auf dem Theken-Terminal in der Küchen-/Theken-Ansicht "
                "„Bon“ tippen. Es öffnet sich der Druckdialog – Standarddrucker (Ubuntu/Windows) wählen.",
            }
        )
    try:
        # Testbon: immer genau eine Kopie, reine ESC/POS-Bytes
        cfg = dict(cfg)
        cfg["copies"] = 1
        payload = build_test_ticket(name)
        target = send_to_printer(cfg, payload, station_id=station_id)
        return jsonify({"ok": True, "target": target, "bytes": len(payload)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@printers_bp.route(
    "/station/<int:station_id>/orders/<int:order_id>/ticket",
    methods=["GET"],
)
def station_order_ticket(station_id, order_id):
    """ESC/POS-Bon als Base64 – fuer lokalen Print-Agent auf dem Terminal."""
    conn = get_db_connection()
    payload = build_station_ticket_payload(conn, order_id, station_id)
    conn.close()
    if not payload:
        return jsonify({"ok": False, "error": "no station items"}), 404
    return jsonify(payload)


@printers_bp.route(
    "/station/<int:station_id>/orders/<int:order_id>/print",
    methods=["POST"],
)
def station_reprint(station_id, order_id):
    conn = get_db_connection()
    try:
        result = print_station_order(conn, order_id, station_id)
    except Exception as exc:
        conn.close()
        return jsonify({"ok": False, "error": str(exc)}), 500
    # Browser/Client: Ticket mitgeben, Terminal-Browser druckt
    if result.get("reason") in ("client_agent", "client_browser"):
        payload = build_station_ticket_payload(conn, order_id, station_id)
        conn.close()
        if not payload:
            return jsonify({"ok": False, "error": "no station items"}), 404
        payload["client_print"] = True
        payload["print_mode"] = "browser"
        return jsonify(payload)
    conn.close()
    if result.get("skipped"):
        return jsonify({"ok": False, "error": result.get("reason") or "skipped"}), 400
    if not result.get("ok"):
        return jsonify(result), 500
    return jsonify(result)
