from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .paths import backups_dir, migrations_dir

_MIGRATION_RE = re.compile(r"^(\d{3,})_(.+)\.sql$")


def available_migrations() -> list[tuple[int, str, Path]]:
    rows: list[tuple[int, str, Path]] = []
    root = migrations_dir()
    if not root.exists():
        return rows
    for path in sorted(root.glob("*.sql")):
        m = _MIGRATION_RE.match(path.name)
        if not m:
            continue
        rows.append((int(m.group(1)), m.group(2), path))
    return rows


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone() is not None


def applied_versions(con: sqlite3.Connection) -> set[int]:
    if not _table_exists(con, "schema_migrations"):
        return set()
    return {int(r[0]) for r in con.execute("SELECT version FROM schema_migrations").fetchall()}


def pending_migrations(con: sqlite3.Connection) -> list[tuple[int, str, Path]]:
    applied = applied_versions(con)
    return [row for row in available_migrations() if row[0] not in applied]


def _has_user_data(con: sqlite3.Connection) -> bool:
    tables = {
        str(r[0])
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    return bool(tables - {"schema_migrations"})


def backup_database(con: sqlite3.Connection, db_file: Path, app_version: str) -> Path | None:
    """Create a consistent SQLite backup using SQLite's backup API.

    The backup is made before any pending release migration is applied.  WAL content
    is included by SQLite rather than by copying the database file byte-for-byte.
    """
    if not db_file.exists() or not _has_user_data(con):
        return None
    out_dir = backups_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    safe_version = re.sub(r"[^0-9A-Za-z._-]+", "_", str(app_version))
    target = out_dir / f"dashboard_pre_{safe_version}_{stamp}.sqlite"
    dest = sqlite3.connect(str(target))
    try:
        con.backup(dest)
    finally:
        dest.close()
    return target


def apply_migrations(con: sqlite3.Connection, db_file: Path, app_version: str) -> dict:
    """Apply release-owned SQL migrations to the persistent runtime database.

    Migration SQL lives under /database/migrations in the replaceable application
    release.  The SQLite database itself lives under /data and is never packaged.
    """
    pending = pending_migrations(con)
    backup_path = backup_database(con, db_file, app_version) if pending else None

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            app_version TEXT NOT NULL
        )
        """
    )
    con.commit()

    applied_now: list[int] = []
    for version, name, path in pending:
        sql = path.read_text(encoding="utf-8")
        # executescript can manage a multi-statement migration atomically when the
        # transaction is included in the script passed to it.
        applied_at = datetime.now(timezone.utc).isoformat()
        escaped_name = name.replace("'", "''")
        escaped_app = str(app_version).replace("'", "''")
        escaped_at = applied_at.replace("'", "''")
        script = (
            "BEGIN IMMEDIATE;\n"
            + sql
            + "\n"
            + f"INSERT INTO schema_migrations(version,name,applied_at,app_version) "
              f"VALUES ({int(version)},'{escaped_name}','{escaped_at}','{escaped_app}');\n"
            + "COMMIT;\n"
        )
        try:
            con.executescript(script)
        except Exception:
            try:
                con.rollback()
            except Exception:
                pass
            raise
        applied_now.append(version)

    return {
        "pending_before": [v for v, _, _ in pending],
        "applied_now": applied_now,
        "backup_path": str(backup_path) if backup_path else None,
        "latest_version": max(applied_versions(con) or {0}),
    }
