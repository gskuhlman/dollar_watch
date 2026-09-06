from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def db_path() -> str:
    p = os.getenv("DOLLAR_DASHBOARD_DB", "data/dashboard.sqlite")
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    return p


def connect():
    con = sqlite3.connect(db_path())
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS overrides (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL,
            note TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    return con


def save_snapshot(payload: dict) -> int:
    con = connect()
    cur = con.execute(
        "INSERT INTO snapshots(captured_at,payload) VALUES (?,?)",
        (datetime.now(timezone.utc).isoformat(), json.dumps(payload, default=str)),
    )
    con.commit()
    rid = cur.lastrowid
    con.close()
    return int(rid)


def recent_snapshots(limit: int = 50) -> list[dict]:
    con = connect()
    rows = con.execute(
        "SELECT id,captured_at,payload FROM snapshots ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    out = []
    for rid, captured, payload in rows:
        d = json.loads(payload)
        d["_id"] = rid
        d["_captured_at"] = captured
        out.append(d)
    return out


def get_overrides(defaults: dict[str, float]) -> dict[str, dict]:
    con = connect()
    rows = con.execute("SELECT key,value,note,updated_at FROM overrides").fetchall()
    con.close()
    existing = {r[0]: {"value": r[1], "note": r[2] or "", "updated_at": r[3]} for r in rows}
    for k, v in defaults.items():
        existing.setdefault(k, {"value": v, "note": "", "updated_at": ""})
    return existing


def set_override(key: str, value: float, note: str = "") -> None:
    con = connect()
    con.execute(
        "INSERT INTO overrides(key,value,note,updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value,note=excluded.note,updated_at=excluded.updated_at",
        (key, float(value), note, datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()


def get_setting(key: str, default=None):
    con = connect()
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    con.close()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return row[0]


def set_setting(key: str, value) -> None:
    con = connect()
    con.execute(
        "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )
    con.commit()
    con.close()
