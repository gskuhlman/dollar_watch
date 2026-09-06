from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .evidence import classify_source
from .run_history import lineage, APP_VERSION, SCHEMA_VERSION


def db_path() -> str:
    p = os.getenv("DOLLAR_DASHBOARD_DB", "data/dashboard.sqlite")
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    return p


def _columns(con, table: str) -> set[str]:
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _ensure_column(con, table: str, column: str, ddl: str) -> None:
    if column not in _columns(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _ensure_events(con) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            category TEXT NOT NULL,
            actor TEXT,
            title TEXT NOT NULL,
            source_url TEXT,
            impact REAL NOT NULL DEFAULT 0,
            notes TEXT,
            verification_status TEXT DEFAULT 'UNVERIFIED',
            source_tier TEXT DEFAULT 'UNSOURCED',
            provenance TEXT DEFAULT 'ANALYST-ENTERED'
        )
    """)
    _ensure_column(con, "events", "verification_status", "TEXT DEFAULT 'UNVERIFIED'")
    _ensure_column(con, "events", "source_tier", "TEXT DEFAULT 'UNSOURCED'")
    _ensure_column(con, "events", "provenance", "TEXT DEFAULT 'ANALYST-ENTERED'")


def connect():
    con = sqlite3.connect(db_path())
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at TEXT NOT NULL,
            payload TEXT NOT NULL,
            run_id TEXT,
            parent_run_id TEXT,
            app_version TEXT,
            schema_version TEXT,
            run_kind TEXT DEFAULT 'ANALYSIS'
        )
    """)
    _ensure_column(con, "snapshots", "run_id", "TEXT")
    _ensure_column(con, "snapshots", "parent_run_id", "TEXT")
    _ensure_column(con, "snapshots", "app_version", "TEXT")
    _ensure_column(con, "snapshots", "schema_version", "TEXT")
    _ensure_column(con, "snapshots", "run_kind", "TEXT DEFAULT 'ANALYSIS'")
    con.execute("""
        CREATE TABLE IF NOT EXISTS overrides (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL,
            note TEXT,
            updated_at TEXT NOT NULL,
            source_url TEXT DEFAULT '',
            verification_status TEXT DEFAULT 'UNVERIFIED',
            source_tier TEXT DEFAULT 'UNSOURCED'
        )
    """)
    _ensure_column(con, "overrides", "source_url", "TEXT DEFAULT ''")
    _ensure_column(con, "overrides", "verification_status", "TEXT DEFAULT 'UNVERIFIED'")
    _ensure_column(con, "overrides", "source_tier", "TEXT DEFAULT 'UNSOURCED'")
    con.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    _ensure_events(con)
    return con


def save_snapshot(payload: dict, run_kind: str = "ANALYSIS") -> int:
    con = connect()
    parent = con.execute("SELECT run_id,id FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    parent_run_id = (parent[0] if parent and parent[0] else (str(parent[1]) if parent else None))
    meta = lineage(parent_run_id=parent_run_id, run_kind=run_kind)
    enriched = dict(payload)
    enriched["run_meta"] = meta
    cur = con.execute(
        "INSERT INTO snapshots(captured_at,payload,run_id,parent_run_id,app_version,schema_version,run_kind) VALUES (?,?,?,?,?,?,?)",
        (meta["captured_at"], json.dumps(enriched, default=str), meta["run_id"], meta["parent_run_id"], APP_VERSION, SCHEMA_VERSION, run_kind),
    )
    con.commit(); rid = cur.lastrowid; con.close(); return int(rid)


def save_snapshot_if_new(payload: dict, source_timestamp: str | None = None, run_kind: str = "AUTO") -> tuple[int|None,bool]:
    """Save one lineage record per distinct collected snapshot timestamp.

    Streamlit reruns frequently; this prevents UI interactions from manufacturing fake market runs.
    """
    con=connect()
    row=con.execute("SELECT id,payload FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        try:
            prior=json.loads(row[1])
            prior_ts=prior.get("timestamp")
            if source_timestamp and prior_ts == source_timestamp:
                con.close(); return int(row[0]),False
        except Exception:
            pass
    con.close()
    return save_snapshot(payload,run_kind=run_kind),True


def recent_snapshots(limit: int = 50) -> list[dict]:
    con = connect()
    rows = con.execute("SELECT id,captured_at,payload,run_id,parent_run_id,app_version,schema_version,run_kind FROM snapshots ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    con.close(); out=[]
    for rid,captured,payload,run_id,parent_run_id,app_version,schema_version,run_kind in rows:
        d=json.loads(payload)
        legacy = not bool(run_id and app_version and schema_version)
        d["_id"]=rid; d["_captured_at"]=captured
        d["_run_id"]=run_id or f"legacy-{rid}"
        d["_parent_run_id"]=parent_run_id
        d["_app_version"]=app_version or "LEGACY"
        d["_schema_version"]=schema_version or "LEGACY"
        d["_run_kind"]="LEGACY_BASELINE" if legacy else (run_kind or "ANALYSIS")
        d["_legacy_lineage"]=legacy
        out.append(d)
    return out


def get_overrides(defaults: dict[str, float]) -> dict[str, dict]:
    con = connect()
    rows = con.execute("SELECT key,value,note,updated_at,source_url,verification_status,source_tier FROM overrides").fetchall()
    con.close()
    existing = {
        r[0]: {"value": r[1], "note": r[2] or "", "updated_at": r[3], "source_url": r[4] or "", "verification_status": r[5] or "UNVERIFIED", "source_tier": r[6] or "UNSOURCED"}
        for r in rows
    }
    for k,v in defaults.items():
        existing.setdefault(k, {"value":v,"note":"","updated_at":"","source_url":"","verification_status":"UNVERIFIED","source_tier":"UNSOURCED"})
    return existing


def set_override(key: str, value: float, note: str = "", source_url: str = "", verification_status: str = "UNVERIFIED") -> None:
    con=connect(); tier=classify_source(source_url).get("source_tier","UNSOURCED")
    con.execute(
        "INSERT INTO overrides(key,value,note,updated_at,source_url,verification_status,source_tier) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value,note=excluded.note,updated_at=excluded.updated_at,source_url=excluded.source_url,verification_status=excluded.verification_status,source_tier=excluded.source_tier",
        (key,float(value),note,datetime.now(timezone.utc).isoformat(),source_url,verification_status,tier),
    )
    con.commit(); con.close()


def get_setting(key: str, default=None):
    con=connect(); row=con.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone(); con.close()
    if not row: return default
    try: return json.loads(row[0])
    except Exception: return row[0]


def set_setting(key: str, value) -> None:
    con=connect(); con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,json.dumps(value))); con.commit(); con.close()


def add_event(
    category: str, actor: str, title: str, source_url: str = "", impact: float = 0.0, notes: str = "",
    verification_status: str = "UNVERIFIED", provenance: str = "ANALYST-ENTERED",
) -> int:
    con=connect(); _ensure_events(con); tier=classify_source(source_url).get("source_tier","UNSOURCED")
    cur=con.execute(
        "INSERT INTO events(created_at,category,actor,title,source_url,impact,notes,verification_status,source_tier,provenance) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(),category,actor,title,source_url,float(impact),notes,verification_status,tier,provenance),
    )
    con.commit(); rid=int(cur.lastrowid); con.close(); return rid


def recent_events(limit: int = 100) -> list[dict]:
    con=connect(); _ensure_events(con)
    rows=con.execute(
        "SELECT id,created_at,category,actor,title,source_url,impact,notes,verification_status,source_tier,provenance FROM events ORDER BY id DESC LIMIT ?",(limit,)
    ).fetchall(); con.close()
    keys=["id","created_at","category","actor","title","source_url","impact","notes","verification_status","source_tier","provenance"]
    return [dict(zip(keys,r)) for r in rows]


def save_alerts(alerts: list[dict]) -> None:
    if not alerts: return
    con=connect(); con.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            severity TEXT NOT NULL,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            payload TEXT
        )
    """)
    for a in alerts:
        con.execute("INSERT INTO alerts(created_at,severity,kind,message,payload) VALUES (?,?,?,?,?)",(datetime.now(timezone.utc).isoformat(),a.get("severity","INFO"),a.get("kind","general"),a.get("message",""),json.dumps(a,default=str)))
    con.commit(); con.close()


def recent_alerts(limit: int = 100) -> list[dict]:
    con=connect(); con.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            severity TEXT NOT NULL,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            payload TEXT
        )
    """)
    rows=con.execute("SELECT id,created_at,severity,kind,message,payload FROM alerts ORDER BY id DESC LIMIT ?",(limit,)).fetchall(); con.close(); out=[]
    for rid,created,severity,kind,message,payload in rows:
        d={"id":rid,"created_at":created,"severity":severity,"kind":kind,"message":message}
        try: d["payload"]=json.loads(payload) if payload else {}
        except Exception: d["payload"]={}
        out.append(d)
    return out
