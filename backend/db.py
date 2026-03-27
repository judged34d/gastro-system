# ============================================================
# [1000] DATABASE MODULE
# ============================================================
import sqlite3

DB_PATH = "/opt/gastro-system/data/database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
