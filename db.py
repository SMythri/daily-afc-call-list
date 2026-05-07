import os
import sqlite3


def get_db_path() -> str:
    return os.getenv("DATABASE_PATH", "storage/afc_call_list.db")


def get_connection():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
