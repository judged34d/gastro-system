#!/usr/bin/env python3
"""
Loescht alle Orders des aktiven Events (SQLite direkt, gleiche Logik wie POST /admin/events/clear-orders).

Auf dem Pi z. B.:
  export GASTRO_DB_PATH=/opt/gastro-system/data/database.db
  python3 tools/cleanup_active_event_orders.py

Oder per HTTP (nach Deploy):
  curl -X POST http://127.0.0.1:8000/admin/events/clear-orders -H "Content-Type: application/json" -d "{}"
"""

from __future__ import annotations

import os
import sys

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, BACKEND)

from db import get_active_event_id, get_db_connection, purge_orders_for_event  # noqa: E402


def main() -> None:
    conn = get_db_connection()
    eid = get_active_event_id(conn)
    if not eid:
        print("Kein aktives Event.", file=sys.stderr)
        sys.exit(1)
    print(f"Aktives Event id={eid}: loesche alle Orders ...")
    n = purge_orders_for_event(conn, eid)
    conn.close()
    print(f"OK, {n} Orders geloescht.")


if __name__ == "__main__":
    main()
