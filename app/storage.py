import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "calculations.sqlite3"


def connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


def save_calculation(name, items):
    payload = json.dumps(items, ensure_ascii=False)
    with connect() as db:
        db.execute(
            "INSERT INTO calculations(name, payload, created_at) VALUES (?, ?, ?)",
            (name, payload, datetime.now().isoformat(timespec="minutes"))
        )


def list_calculations():
    with connect() as db:
        rows = db.execute(
            "SELECT name, payload, created_at FROM calculations ORDER BY id DESC"
        ).fetchall()
    return [
        {"name": name, "items_count": len(json.loads(payload)), "created_at": created_at}
        for name, payload, created_at in rows
    ]
