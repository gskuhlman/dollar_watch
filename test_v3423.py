from __future__ import annotations

import sqlite3
from pathlib import Path

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION, SCORE_MODEL_VERSION, SCHEMA_VERSION
from dollar_dashboard.paths import database_path, policy_cache_path, install_root
from dollar_dashboard.storage import connect, database_status


def test_v3423_lineage():
    assert __version__ == "3.4.25"
    assert APP_VERSION == "3.4.25"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.3"


def test_default_runtime_paths_are_install_root_anchored(monkeypatch):
    monkeypatch.delenv("DOLLAR_WATCH_DATA_DIR", raising=False)
    monkeypatch.delenv("DOLLAR_DASHBOARD_DB", raising=False)
    monkeypatch.delenv("DOLLAR_POLICY_CACHE", raising=False)
    assert database_path() == (install_root() / "data" / "dashboard.sqlite").resolve()
    assert policy_cache_path() == (install_root() / "data" / "official_policy_cache.json").resolve()


def test_relative_overrides_are_install_root_anchored(monkeypatch):
    monkeypatch.setenv("DOLLAR_DASHBOARD_DB", "persistent/custom.sqlite")
    monkeypatch.setenv("DOLLAR_POLICY_CACHE", "persistent/policy.json")
    assert database_path() == (install_root() / "persistent" / "custom.sqlite").resolve()
    assert policy_cache_path() == (install_root() / "persistent" / "policy.json").resolve()


def test_existing_database_is_migrated_in_place_and_backed_up(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    db = data_dir / "dashboard.sqlite"
    data_dir.mkdir(parents=True)
    legacy = sqlite3.connect(db)
    legacy.execute("CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, captured_at TEXT NOT NULL, payload TEXT NOT NULL)")
    legacy.execute("INSERT INTO snapshots(captured_at,payload) VALUES (?,?)", ("2026-08-01T00:00:00+00:00", '{"timestamp":"2026-08-01T00:00:00+00:00"}'))
    legacy.commit()
    legacy.close()

    monkeypatch.setenv("DOLLAR_WATCH_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DOLLAR_DASHBOARD_DB", str(db))
    monkeypatch.delenv("DOLLAR_POLICY_CACHE", raising=False)

    con = connect()
    count = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    versions = [r[0] for r in con.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()]
    cols = {r[1] for r in con.execute("PRAGMA table_info(snapshots)").fetchall()}
    con.close()

    assert count == 1
    assert versions == [1, 2]
    assert {"run_id", "parent_run_id", "app_version", "schema_version", "run_kind"}.issubset(cols)
    backups = list((data_dir / "backups").glob("dashboard_pre_3.4.25_*.sqlite"))
    assert len(backups) == 1
    check = sqlite3.connect(backups[0])
    assert check.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
    check.close()

    # A second startup has no pending release migration, so it must not create
    # another pre-migration backup.
    con = connect(); con.close()
    assert len(list((data_dir / "backups").glob("dashboard_pre_3.4.25_*.sqlite"))) == 1


def test_database_status_reports_persistent_history(monkeypatch, tmp_path):
    data_dir = tmp_path / "state"
    db = data_dir / "dashboard.sqlite"
    monkeypatch.setenv("DOLLAR_WATCH_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DOLLAR_DASHBOARD_DB", str(db))
    con = connect()
    con.execute("INSERT INTO snapshots(captured_at,payload,app_version,schema_version) VALUES (?,?,?,?)", ("2026-09-01T00:00:00+00:00", "{}", "3.4.23", "3.4.1"))
    con.commit(); con.close()
    status = database_status()
    assert status["database_path"] == str(db.resolve())
    assert status["snapshot_count"] == 1
    assert status["oldest_snapshot"].startswith("2026-09-01")
    assert status["database_migration_version"] == 2
