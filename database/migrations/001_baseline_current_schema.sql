-- V3.4.23 persistent-database baseline.
-- CREATE IF NOT EXISTS preserves every existing row in an upgraded installation.
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    run_id TEXT,
    parent_run_id TEXT,
    app_version TEXT,
    schema_version TEXT,
    run_kind TEXT DEFAULT 'ANALYSIS'
);

CREATE TABLE IF NOT EXISTS overrides (
    key TEXT PRIMARY KEY,
    value REAL NOT NULL,
    note TEXT,
    updated_at TEXT NOT NULL,
    source_url TEXT DEFAULT '',
    verification_status TEXT DEFAULT 'UNVERIFIED',
    source_tier TEXT DEFAULT 'UNSOURCED'
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

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
);

CREATE TABLE IF NOT EXISTS verification_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    claim TEXT NOT NULL,
    bucket TEXT,
    source_url TEXT NOT NULL,
    source_tier TEXT DEFAULT 'UNSOURCED',
    verdict TEXT NOT NULL,
    explanation TEXT,
    model TEXT,
    provenance TEXT DEFAULT 'LLM-ASSISTED',
    relevance_score REAL,
    relevance_status TEXT DEFAULT 'UNKNOWN',
    quarantine_status TEXT DEFAULT 'ACTIVE',
    quarantine_reason TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    severity TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS verification_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_key TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    priority TEXT,
    bucket TEXT,
    claim TEXT NOT NULL,
    headline_source TEXT,
    headline_url TEXT,
    preferred_source TEXT,
    status TEXT DEFAULT 'QUEUED',
    candidate_url TEXT,
    candidate_tier TEXT,
    candidate_relevance REAL,
    relevance_status TEXT,
    llm_verdict TEXT,
    llm_explanation TEXT,
    approved_status TEXT DEFAULT 'UNVERIFIED',
    effect_target TEXT,
    effect_direction REAL DEFAULT 0,
    effect_weight REAL DEFAULT 0,
    action_class TEXT,
    structured_fact INTEGER DEFAULT 0
);
