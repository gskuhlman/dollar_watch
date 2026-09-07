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


def _ensure_verification_checks(con) -> None:
    con.execute("""
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
        )
    """)
    _ensure_column(con, "verification_checks", "relevance_score", "REAL")
    _ensure_column(con, "verification_checks", "relevance_status", "TEXT DEFAULT 'UNKNOWN'")
    _ensure_column(con, "verification_checks", "quarantine_status", "TEXT DEFAULT 'ACTIVE'")
    _ensure_column(con, "verification_checks", "quarantine_reason", "TEXT")


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
    _ensure_verification_checks(con)
    _ensure_verification_queue(con)
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


def save_verification_check(claim: str, bucket: str, source_url: str, verdict: str, explanation: str = "", model: str = "", relevance_score: float|None = None, relevance_status: str = "RELEVANT") -> int:
    con=connect(); _ensure_verification_checks(con)
    tier=classify_source(source_url).get("source_tier","UNSOURCED")
    rel=str(relevance_status or "UNKNOWN").upper()
    qstatus="ACTIVE" if rel=="RELEVANT" else "QUARANTINED"
    qreason="" if qstatus=="ACTIVE" else "Source did not pass semantic relevance gate"
    cur=con.execute(
        "INSERT INTO verification_checks(created_at,claim,bucket,source_url,source_tier,verdict,explanation,model,provenance,relevance_score,relevance_status,quarantine_status,quarantine_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(),claim,bucket,source_url,tier,verdict,explanation,model,"LLM-ASSISTED",relevance_score,rel,qstatus,qreason),
    )
    con.commit(); rid=int(cur.lastrowid); con.close(); return rid


def recent_verification_checks(limit: int = 100, include_quarantined: bool = False) -> list[dict]:
    con=connect(); _ensure_verification_checks(con); _ensure_verification_queue(con); _sync_verification_quarantine(con); con.commit()
    where="" if include_quarantined else "WHERE COALESCE(quarantine_status,'ACTIVE') <> 'QUARANTINED'"
    rows=con.execute(
        f"SELECT id,created_at,claim,bucket,source_url,source_tier,verdict,explanation,model,provenance,relevance_score,relevance_status,quarantine_status,quarantine_reason FROM verification_checks {where} ORDER BY id DESC LIMIT ?",(limit,)
    ).fetchall(); con.close()
    keys=["id","created_at","claim","bucket","source_url","source_tier","verdict","explanation","model","provenance","relevance_score","relevance_status","quarantine_status","quarantine_reason"]
    return [dict(zip(keys,r)) for r in rows]


def recent_quarantined_verification_checks(limit: int = 100) -> list[dict]:
    con=connect(); _ensure_verification_checks(con); _ensure_verification_queue(con); _sync_verification_quarantine(con); con.commit()
    rows=con.execute(
        "SELECT id,created_at,claim,bucket,source_url,source_tier,verdict,explanation,model,provenance,relevance_score,relevance_status,quarantine_status,quarantine_reason FROM verification_checks WHERE COALESCE(quarantine_status,'ACTIVE')='QUARANTINED' ORDER BY id DESC LIMIT ?",(limit,)
    ).fetchall(); con.close()
    keys=["id","created_at","claim","bucket","source_url","source_tier","verdict","explanation","model","provenance","relevance_score","relevance_status","quarantine_status","quarantine_reason"]
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


def _ensure_verification_queue(con) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS verification_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_key TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            priority TEXT, bucket TEXT, claim TEXT NOT NULL, headline_source TEXT, headline_url TEXT,
            preferred_source TEXT, status TEXT DEFAULT 'QUEUED', candidate_url TEXT, candidate_tier TEXT,
            candidate_relevance REAL, relevance_status TEXT, llm_verdict TEXT, llm_explanation TEXT, approved_status TEXT DEFAULT 'UNVERIFIED', effect_target TEXT, effect_direction REAL DEFAULT 0, effect_weight REAL DEFAULT 0
        )
    """)
    # Forward-compatible migration for databases created before V2.7.
    cols={r[1] for r in con.execute("PRAGMA table_info(verification_queue)").fetchall()}
    if "candidate_relevance" not in cols:
        con.execute("ALTER TABLE verification_queue ADD COLUMN candidate_relevance REAL")
    if "relevance_status" not in cols:
        con.execute("ALTER TABLE verification_queue ADD COLUMN relevance_status TEXT")
    if "effect_target" not in cols: con.execute("ALTER TABLE verification_queue ADD COLUMN effect_target TEXT")
    if "effect_direction" not in cols: con.execute("ALTER TABLE verification_queue ADD COLUMN effect_direction REAL DEFAULT 0")
    if "effect_weight" not in cols: con.execute("ALTER TABLE verification_queue ADD COLUMN effect_weight REAL DEFAULT 0")
    if "action_class" not in cols: con.execute("ALTER TABLE verification_queue ADD COLUMN action_class TEXT")
    if "structured_fact" not in cols: con.execute("ALTER TABLE verification_queue ADD COLUMN structured_fact INTEGER DEFAULT 0")

def _sync_verification_quarantine(con) -> int:
    """Quarantine legacy checks whose queue candidate now fails V2.9 relevance rules.

    This is intentionally conservative: only checks that can be matched back to a queue row
    by claim + candidate/source URL are automatically quarantined.  Unmatched historical checks
    remain visible but are not promoted to verified analyst evidence automatically.
    """
    _ensure_verification_checks(con); _ensure_verification_queue(con)
    cur=con.execute("""
        UPDATE verification_checks
           SET quarantine_status='QUARANTINED',
               quarantine_reason='Source candidate failed semantic relevance gate in verification queue',
               relevance_status=COALESCE(NULLIF(relevance_status,''),'IRRELEVANT_SOURCE')
         WHERE id IN (
            SELECT vc.id
              FROM verification_checks vc
              JOIN verification_queue vq
                ON lower(trim(vc.claim))=lower(trim(vq.claim))
               AND lower(trim(vc.source_url))=lower(trim(COALESCE(vq.candidate_url,'')))
             WHERE COALESCE(vq.relevance_status,'') <> 'RELEVANT'
                OR COALESCE(vq.status,'')='IRRELEVANT_SOURCE'
         )
    """)
    return int(cur.rowcount or 0)


def upsert_verification_queue(rows: list[dict]) -> int:
    import hashlib
    con=connect(); _ensure_verification_queue(con); n=0; now=datetime.now(timezone.utc).isoformat()
    for r in rows or []:
        claim=str(r.get('claim') or '').strip(); bucket=str(r.get('bucket') or '').strip(); url=str(r.get('link') or '').strip()
        if len(claim)<10 or not bucket: continue
        key=hashlib.sha256((bucket+'|'+claim).encode('utf-8')).hexdigest()
        status=str(r.get('status') or 'QUEUED')
        candidate_url=str(r.get('candidate_url') or '')
        candidate_tier=str(r.get('candidate_tier') or '')
        candidate_relevance=r.get('candidate_relevance')
        relevance_status=str(r.get('relevance_status') or '')
        structured=1 if r.get('structured_fact') else 0
        con.execute("""INSERT INTO verification_queue(claim_key,created_at,updated_at,priority,bucket,claim,headline_source,headline_url,preferred_source,status,candidate_url,candidate_tier,candidate_relevance,relevance_status,effect_target,effect_direction,effect_weight,action_class,structured_fact)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(claim_key) DO UPDATE SET updated_at=excluded.updated_at,priority=excluded.priority,headline_source=excluded.headline_source,headline_url=excluded.headline_url,preferred_source=excluded.preferred_source,effect_target=excluded.effect_target,effect_direction=excluded.effect_direction,effect_weight=excluded.effect_weight,action_class=excluded.action_class,structured_fact=excluded.structured_fact,candidate_url=CASE WHEN excluded.candidate_url<>'' THEN excluded.candidate_url ELSE verification_queue.candidate_url END,candidate_tier=CASE WHEN excluded.candidate_tier<>'' THEN excluded.candidate_tier ELSE verification_queue.candidate_tier END,candidate_relevance=COALESCE(excluded.candidate_relevance,verification_queue.candidate_relevance),relevance_status=CASE WHEN excluded.relevance_status<>'' THEN excluded.relevance_status ELSE verification_queue.relevance_status END,status=CASE WHEN excluded.status='STRUCTURED_VERIFIED' THEN excluded.status WHEN excluded.status='SOURCE_FOUND' AND verification_queue.status IN ('QUEUED','NO_CANDIDATE','ERROR','IRRELEVANT_SOURCE') THEN excluded.status ELSE verification_queue.status END""",
        (key,now,now,r.get('priority'),bucket,claim,r.get('source'),url,r.get('preferred_verification_source'),status,candidate_url,candidate_tier,candidate_relevance,relevance_status,r.get('effect_target',''),float(r.get('effect_direction') or 0),float(r.get('effect_weight') or 0),r.get('action_class',''),structured)); n+=1
    con.commit(); con.close(); return n

def recent_verification_queue(limit:int=100) -> list[dict]:
    con=connect(); _ensure_verification_queue(con)
    rows=con.execute("SELECT id,created_at,updated_at,priority,bucket,claim,headline_source,headline_url,preferred_source,status,candidate_url,candidate_tier,candidate_relevance,relevance_status,llm_verdict,llm_explanation,approved_status,effect_target,effect_direction,effect_weight,action_class,structured_fact FROM verification_queue ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END, updated_at DESC LIMIT ?",(limit,)).fetchall(); con.close()
    keys=['id','created_at','updated_at','priority','bucket','claim','headline_source','headline_url','preferred_source','status','candidate_url','candidate_tier','candidate_relevance','relevance_status','llm_verdict','llm_explanation','approved_status','effect_target','effect_direction','effect_weight','action_class','structured_fact']
    return [dict(zip(keys,r)) for r in rows]

def update_verification_queue_check(queue_id:int,candidate_url:str='',candidate_tier:str='',verdict:str='',explanation:str='',status:str='CHECKED',candidate_relevance:float|None=None,relevance_status:str='') -> None:
    con=connect(); _ensure_verification_queue(con)
    con.execute("UPDATE verification_queue SET updated_at=?,candidate_url=?,candidate_tier=?,candidate_relevance=?,relevance_status=?,llm_verdict=?,llm_explanation=?,status=? WHERE id=?",(datetime.now(timezone.utc).isoformat(),candidate_url,candidate_tier,candidate_relevance,relevance_status,verdict,explanation,status,int(queue_id))); con.commit(); con.close()


def update_verification_queue_approval(queue_id:int,approved_status:str) -> None:
    allowed={"UNVERIFIED","APPROVED","REJECTED","DISPUTED"}
    status=str(approved_status or "UNVERIFIED").upper()
    if status not in allowed:
        raise ValueError(f"Invalid approval status: {status}")
    con=connect(); _ensure_verification_queue(con)
    con.execute("UPDATE verification_queue SET updated_at=?,approved_status=? WHERE id=?",(datetime.now(timezone.utc).isoformat(),status,int(queue_id)))
    con.commit(); con.close()


def approved_verification_evidence(limit:int=100) -> list[dict]:
    """Human-approved, source-relevant, LLM-supported checks eligible for bounded score effects.

    Approval is the explicit promotion gate.  CONTRADICTED/INCONCLUSIVE checks remain audit data and
    do not invert a claim automatically.
    """
    con=connect(); _ensure_verification_queue(con)
    rows=con.execute("""SELECT id,updated_at,priority,bucket,claim,candidate_url,candidate_tier,candidate_relevance,relevance_status,llm_verdict,approved_status,effect_target,effect_direction,effect_weight,action_class
      FROM verification_queue WHERE approved_status='APPROVED' AND relevance_status='RELEVANT' AND upper(COALESCE(llm_verdict,''))='SUPPORTED'
      ORDER BY updated_at DESC LIMIT ?""",(limit,)).fetchall(); con.close()
    keys=['id','updated_at','priority','bucket','claim','source_url','source_tier','relevance_score','relevance_status','verdict','approved_status','effect_target','effect_direction','effect_weight','action_class']
    return [dict(zip(keys,r)) for r in rows]
