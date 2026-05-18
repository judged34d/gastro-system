"""Globale Betriebsmodi (app_settings)."""


def _flag_from_row(row) -> bool:
    if not row:
        return False
    val = str(row["value"] or "0").strip().lower()
    return val in ("1", "true", "yes", "on")


def is_single_terminal_mode(conn) -> bool:
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'single_terminal_mode'"
    ).fetchone()
    return _flag_from_row(row)


def initial_station_status(conn) -> str:
    return "ready" if is_single_terminal_mode(conn) else "new"
