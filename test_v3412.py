from pathlib import Path

from dollar_dashboard import __version__
from dollar_dashboard.evidence import canonical_verification_label, summarize_verification_records
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION
from dollar_dashboard.storage import (
    save_verification_check,
    recent_verification_checks,
    verification_check_summary_full,
    upsert_verification_queue,
    recent_verification_queue,
    verification_queue_summary_full,
    connect,
)


def test_v3412_version_lineage_unchanged_score_model():
    assert __version__ == "3.4.27"
    assert APP_VERSION == "3.4.27"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.4"


def test_legacy_verdict_variants_canonicalize_without_becoming_new_evidence_categories():
    assert canonical_verification_label("CONTRICTED") == "CONTRADICTED"
    assert canonical_verification_label(" inconclusive: ") == "INCONCLUSIVE"
    rows=[
        {"claim":"a","verdict":"CONTRICTED"},
        {"claim":"b","verdict":"INCONCLUSIVE:"},
        {"claim":"c","verdict":"SUPPORTED"},
    ]
    out=summarize_verification_records(rows)
    assert out["verdict_counts"] == {"CONTRADICTED":1,"INCONCLUSIVE":1,"SUPPORTED":1}
    assert out["raw_label_anomalies"]["CONTRICTED"]["canonical"] == "CONTRADICTED"
    assert out["raw_label_anomalies"]["INCONCLUSIVE:"]["canonical"] == "INCONCLUSIVE"


def test_full_persisted_check_summary_is_not_capped_by_recent_detail_window(tmp_path, monkeypatch):
    monkeypatch.setenv("DOLLAR_DASHBOARD_DB", str(tmp_path / "checks.sqlite"))
    for i in range(54):
        save_verification_check(f"claim number {i} long enough", "TEST", "https://www.federalreserve.gov/test", "INCONCLUSIVE")
    save_verification_check("legacy contradicted claim", "TEST", "https://www.federalreserve.gov/test", "CONTRADICTED")
    # Simulate a legacy typo already persisted in an older database.
    con=connect(); con.execute("UPDATE verification_checks SET verdict='CONTRICTED' WHERE claim='legacy contradicted claim'"); con.commit(); con.close()
    assert len(recent_verification_checks(50)) == 50
    out=verification_check_summary_full()
    assert out["complete_population"] is True
    assert out["scope"] == "ALL_ACTIVE_PERSISTED_SOURCE_CHECKS"
    assert out["total"] == 55
    assert out["verdict_counts"]["INCONCLUSIVE"] == 54
    assert out["verdict_counts"]["CONTRADICTED"] == 1
    assert out["raw_label_anomalies"]["CONTRICTED"]["canonical"] == "CONTRADICTED"


def test_full_queue_summary_is_not_capped_at_100(tmp_path, monkeypatch):
    monkeypatch.setenv("DOLLAR_DASHBOARD_DB", str(tmp_path / "queue.sqlite"))
    rows=[{"claim":f"verification queue claim number {i}","bucket":"TEST","status":"QUEUED"} for i in range(105)]
    upsert_verification_queue(rows)
    assert len(recent_verification_queue(100)) == 100
    out=verification_queue_summary_full()
    assert out["complete_population"] is True
    assert out["scope"] == "ALL_VERIFICATION_QUEUE_ROWS"
    assert out["total"] == 105
    assert out["status_counts"]["QUEUED"] == 105
    assert out["verdict_counts"]["UNKNOWN"] == 105


def test_llm_has_market_pricing_decay_and_full_population_guardrails():
    src=Path("dollar_dashboard/llm.py").read_text(encoding="utf-8")
    assert "FULL-POPULATION database aggregates" in src
    assert "raw_label_anomalies" in src
    assert "MARKET-PRICING INFERENCE RULE" in src
    assert "POSITIONING-DECAY RULE" in src
    assert "ANTI-CHASE LANGUAGE RULE" in src


def test_app_uses_full_database_summaries_but_keeps_detail_lists_capped():
    src=Path("app.py").read_text(encoding="utf-8")
    assert '"verification_check_summary":verification_check_summary_full()' in src
    assert '"verification_queue_state_summary":verification_queue_summary_full()' in src
    assert "persisted_checks=recent_verification_checks(50)" in src
