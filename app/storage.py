import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

# Flet 0.86 runs packaged apps from a writable app-private working directory.
# Keep the database out of the read-only APK bundle (where __file__ points).
DATA_DIR = Path(os.environ.get("FLET_APP_STORAGE_DATA") or Path.cwd())
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "calculations.sqlite3"


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
