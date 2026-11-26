import json
import os
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Flet 0.86 runs packaged apps from a writable app-private working directory.
# Keep the database out of the read-only APK bundle (where __file__ points).
DATA_DIR = Path(os.environ.get("FLET_APP_STORAGE_DATA") or Path.cwd())
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "calculations.sqlite3"

_DECIMAL_MARKER = "__decimal__"


class DecimalJSONEncoder(json.JSONEncoder):
    """JSON encoder that keeps Decimal values exact (used by saved drafts)."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return {_DECIMAL_MARKER: str(obj)}
        return super().default(obj)


def restore_decimals(value):
    """Turn ``{"__decimal__": "..."}`` markers back into Decimal objects."""
    if isinstance(value, dict):
        if set(value) == {_DECIMAL_MARKER}:
            try:
                return Decimal(value[_DECIMAL_MARKER])
            except (InvalidOperation, TypeError, ValueError):
                return value[_DECIMAL_MARKER]
        return {key: restore_decimals(item) for key, item in value.items()}
    if isinstance(value, list):
        return [restore_decimals(item) for item in value]
    return value


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
        # Drafts keep the current state of every calculation screen so it can
        # be restored after the app was closed or the phone was powered off.
        db.execute("""
            CREATE TABLE IF NOT EXISTS drafts (
                screen TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS parties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                counterparty TEXT NOT NULL DEFAULT '{}',
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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


def save_draft(screen, state):
    """Persist the current state of a calculation screen."""
    payload = json.dumps(state, ensure_ascii=False, cls=DecimalJSONEncoder)
    updated_at = datetime.now().isoformat(timespec="seconds")
    with connect() as db:
        db.execute(
            """
            INSERT INTO drafts(screen, payload, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(screen) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (screen, payload, updated_at),
        )


def load_draft(screen):
    """Return the last saved state of a calculation screen, or ``None``."""
    with connect() as db:
        row = db.execute(
            "SELECT payload FROM drafts WHERE screen = ?", (screen,)
        ).fetchone()
    if not row:
        return None
    try:
        state = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None
    return restore_decimals(state)


def clear_draft(screen):
    with connect() as db:
        db.execute("DELETE FROM drafts WHERE screen = ?", (screen,))


def save_party(party_type, name, description, counterparty, payload):
    """Create a party and return its id."""
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as db:
        cursor = db.execute(
            """INSERT INTO parties
               (type, name, description, counterparty, payload, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                party_type, name, description[:500],
                json.dumps(counterparty, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False, cls=DecimalJSONEncoder),
                now, now,
            ),
        )
        return cursor.lastrowid


def list_parties():
    with connect() as db:
        rows = db.execute(
            """SELECT id, type, name, description, counterparty, payload,
                      created_at, updated_at
               FROM parties ORDER BY updated_at DESC, id DESC"""
        ).fetchall()
    result = []
    for row in rows:
        party_id, party_type, name, description, counterparty, payload, created, updated = row
        try:
            counterparty = json.loads(counterparty)
            payload = restore_decimals(json.loads(payload))
        except (json.JSONDecodeError, TypeError):
            counterparty, payload = {}, []
        result.append({
            "id": party_id, "type": party_type, "name": name,
            "description": description, "counterparty": counterparty,
            "payload": payload, "created_at": created, "updated_at": updated,
        })
    return result


def delete_party(party_id):
    with connect() as db:
        db.execute("DELETE FROM parties WHERE id = ?", (party_id,))


def update_party(party_id, name, description, counterparty, payload):
    """Update an existing party and its last-modified timestamp."""
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as db:
        db.execute(
            """UPDATE parties SET name = ?, description = ?, counterparty = ?,
                      payload = ?, updated_at = ? WHERE id = ?""",
            (
                name.strip(), description[:500],
                json.dumps(counterparty, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False, cls=DecimalJSONEncoder),
                now, party_id,
            ),
        )
