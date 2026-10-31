from pathlib import Path

from dollar_dashboard import __version__
from dollar_dashboard.evidence import canonical_verification_label, summarize_verification_records
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION


def test_v3413_version_lineage_unchanged_score_model():
    assert __version__ == "3.4.27"
    assert APP_VERSION == "3.4.27"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.4"


def test_wrapped_legacy_verdicts_canonicalize_before_counting():
    assert canonical_verification_label("VERDICT:_INCONCLUSIVE") == "INCONCLUSIVE"
    assert canonical_verification_label("result: contradicted") == "CONTRADICTED"
    assert canonical_verification_label("OUTCOME=SUPPORTED") == "SUPPORTED"
    rows = [
        {"claim":"a","verdict":"VERDICT:_INCONCLUSIVE"},
        {"claim":"b","verdict":"INCONCLUSIVE"},
        {"claim":"c","verdict":"CONTRICTED"},
        {"claim":"d","verdict":"SUPPORTED"},
    ]
    out = summarize_verification_records(rows, complete=True)
    assert out["verdict_counts"] == {"INCONCLUSIVE":2,"CONTRADICTED":1,"SUPPORTED":1}
    assert "VERDICT:_INCONCLUSIVE" in out["raw_label_anomalies"]
    assert out["raw_label_anomalies"]["VERDICT:_INCONCLUSIVE"]["canonical"] == "INCONCLUSIVE"
    assert out["verdict_count_sum"] == 4
    assert out["verdict_counts_reconcile"] is True
    assert out["accounting_reconciles"] is True


def test_complete_population_accounting_exposes_independent_reconciliation_totals():
    rows = [
        {"claim":"a","verdict":"SUPPORTED","status":"CHECKED","relevance_status":"RELEVANT"},
        {"claim":"b","verdict":"UNKNOWN","status":"QUEUED","relevance_status":"UNKNOWN"},
        {"claim":"c","verdict":"INCONCLUSIVE","status":"IRRELEVANT_SOURCE","relevance_status":"IRRELEVANT_SOURCE"},
    ]
    out = summarize_verification_records(rows, complete=True)
    assert out["total"] == 3
    assert out["verdict_count_sum"] == 3
    assert out["status_count_sum"] == 3
    assert out["relevance_count_sum"] == 3
    assert out["verdict_counts_reconcile"] is True
    assert out["status_counts_reconcile"] is True
    assert out["relevance_counts_reconcile"] is True
    assert out["accounting_reconciles"] is True
    assert out["status_counts"]["IRRELEVANT_SOURCE"] == 1


def test_llm_guards_against_partial_verification_breakdowns_and_facility_necessity_claims():
    src = Path("dollar_dashboard/llm.py").read_text(encoding="utf-8")
    assert "VERDICT:_INCONCLUSIVE" in src
    assert "never publish a partial list whose numbers do not add to total" in src
    assert "FUNDING-FACILITY NON-NECESSITY RULE" in src
    assert "NOT necessary conditions" in src
    assert "facility draws" in src
