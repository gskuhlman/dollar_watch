from __future__ import annotations

import os
from pathlib import Path


def install_root() -> Path:
    """Absolute Dollar Watch installation root.

    Runtime paths are anchored here rather than to the process working directory so
    launching from a shortcut, Task Scheduler, VS Code, or another shell directory
    always finds the same persistent state.
    """
    return Path(__file__).resolve().parents[1]


def _resolve_override(env_name: str, default_relative: str) -> Path:
    raw = str(os.getenv(env_name, "") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = install_root() / p
        return p.resolve()
    return (install_root() / default_relative).resolve()


def data_dir() -> Path:
    raw = str(os.getenv("DOLLAR_WATCH_DATA_DIR", "") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = install_root() / p
        return p.resolve()
    return (install_root() / "data").resolve()


def database_path() -> Path:
    raw = str(os.getenv("DOLLAR_DASHBOARD_DB", "") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = install_root() / p
        return p.resolve()
    return data_dir() / "dashboard.sqlite"


def policy_cache_path() -> Path:
    raw = str(os.getenv("DOLLAR_POLICY_CACHE", "") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = install_root() / p
        return p.resolve()
    return data_dir() / "official_policy_cache.json"


def backups_dir() -> Path:
    # If the operator explicitly relocates only the database, keep its automatic
    # backups beside that database unless a full persistent data directory was
    # explicitly configured.
    if str(os.getenv("DOLLAR_WATCH_DATA_DIR", "") or "").strip():
        return data_dir() / "backups"
    if str(os.getenv("DOLLAR_DASHBOARD_DB", "") or "").strip():
        return database_path().parent / "backups"
    return data_dir() / "backups"


def migrations_dir() -> Path:
    return install_root() / "database" / "migrations"


def ensure_runtime_dirs() -> None:
    database_path().parent.mkdir(parents=True, exist_ok=True)
    policy_cache_path().parent.mkdir(parents=True, exist_ok=True)
    backups_dir().mkdir(parents=True, exist_ok=True)
