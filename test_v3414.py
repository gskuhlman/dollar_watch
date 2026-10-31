from pathlib import Path

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION
from dollar_dashboard.scoring import score
from test_v331 import _base, _official, _ovs


def test_v3414_version_lineage_unchanged_score_model():
    assert __version__ == "3.4.27"
    assert APP_VERSION == "3.4.27"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.4"


def test_us_q2_direct_fx_fact_is_not_duplicated_in_deterministic_evidence():
    snap = _base()
    snap["official_policy_meta"] = _official(True)
    out = score(snap, {"scores":{}}, _ovs())
    rows = out["deterministic_verified_evidence"]
    us_rows = [r for r in rows if r.get("action_class") == "US_DIRECT_FX_INTERVENTION"]
    assert len(us_rows) == 1
    assert us_rows[0].get("period") == "2026-Q2"
    assert us_rows[0].get("fact_key") == "US_DIRECT_FX_INTERVENTION|2026-Q2"


def test_deterministic_evidence_summary_matches_unique_analyst_facts():
    snap = _base()
    snap["official_policy_meta"] = _official(True)
    out = score(snap, {"scores":{}}, _ovs())
    rows = out["deterministic_verified_evidence"]
    summary = out["deterministic_evidence_summary"]
    assert summary["total_unique_facts"] == len(rows)
    assert summary["duplicate_fact_keys_present"] is False
    assert sum(summary["action_class_counts"].values()) == len(rows)
    assert summary["action_class_counts"]["US_DIRECT_FX_INTERVENTION"] == 1


def test_llm_uses_authoritative_deterministic_fact_summary_not_canonical_recount():
    src = Path("dollar_dashboard/llm.py").read_text(encoding="utf-8")
    assert "DETERMINISTIC FACT COUNT RULE" in src
    assert "deterministic_evidence_summary is authoritative" in src
    assert "Do not add or recount official_policy_meta.canonical_statements" in src
