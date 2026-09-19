from __future__ import annotations

import pandas as pd

from dollar_dashboard import __version__
from dollar_dashboard import data, llm
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION
from dollar_dashboard.triggers import _auction_lifecycle, _next_auction


def test_v3418_version_keeps_score_model_3417_lineage():
    assert __version__ == "3.4.25"
    assert APP_VERSION == "3.4.25"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.3"


def test_upcoming_merge_prefers_richer_general_row_for_same_cusip_date():
    dedicated = data._normalize_auction_frame(pd.DataFrame([{
        "cusip":"91282ABC1", "security_type":"Note", "security_term":"10-Year",
        "original_security_term":"10-Year", "auction_date":"2026-09-17",
        # Simulate a convenience row that omitted the TIPS flag.
        "inflation_index_security":None, "floating_rate":None,
    }]))
    general = data._normalize_auction_frame(pd.DataFrame([{
        "cusip":"91282ABC1", "security_type":"Note", "security_term":"10-Year",
        "original_security_term":"10-Year", "auction_date":"2026-09-17",
        "inflation_index_security":"Yes", "floating_rate":"No",
    }]))
    merged = data._merge_upcoming_auction_frames(dedicated, general)
    assert len(merged) == 1
    assert merged.iloc[0]["term_key"] == "10-Year TIPS"
    assert merged.iloc[0]["instrument_class"] == "TIPS"
    assert merged.iloc[0]["_calendar_source"] == "auctions_query"


def test_summarized_upcoming_nominal_calendar_excludes_tips_and_carries_class(monkeypatch):
    monkeypatch.setattr(data, "treasury_calendar_date", lambda now=None: pd.Timestamp("2026-09-14").date())
    raw = data._normalize_auction_frame(pd.DataFrame([
        {"cusip":"TIPS1", "security_type":"Note", "security_term":"10-Year", "original_security_term":"10-Year", "inflation_index_security":"Yes", "auction_date":"2026-09-17"},
        {"cusip":"NOM20", "security_type":"Bond", "security_term":"20-Year", "original_security_term":"20-Year", "inflation_index_security":"No", "auction_date":"2026-09-15"},
    ]))
    out=data.summarize_upcoming_auctions(raw,days=10)
    assert list(out["term_key"]) == ["20-Year"]
    assert list(out["instrument_class"]) == ["NOMINAL_COUPON"]


def test_treasury_calendar_date_uses_new_york_not_utc_rollover():
    # 01:46 UTC Sep 15 is still Sep 14 in New York.
    assert data.treasury_calendar_date("2026-09-15T01:46:00Z").isoformat() == "2026-09-14"


def test_auction_lifecycle_uses_treasury_calendar_date_and_ignores_tips_replacement():
    snap={
        "timestamp":"2026-09-15T01:46:00Z",
        "upcoming_auctions":[
            {"auction_date":"2026-09-15","term_key":"20-Year","instrument_class":"NOMINAL_COUPON"},
            {"auction_date":"2026-09-17","term_key":"10-Year TIPS","instrument_class":"TIPS"},
            {"auction_date":"2026-10-08","term_key":"10-Year","instrument_class":"NOMINAL_COUPON"},
        ],
    }
    asof=pd.Timestamp(snap["timestamp"])
    nxt=_next_auction(snap,"10-Year",asof)
    assert pd.Timestamp(nxt).date().isoformat() == "2026-10-08"
    life=_auction_lifecycle(snap,{"auction_date":"2026-09-09"},"10-Year",asof)
    assert life["age_days"] == 5.0  # Sep 14 NY date minus Sep 9
    assert life["lifecycle"] == "FRESH"  # Sep 17 TIPS cannot make nominal 10Y pending replacement


def test_llm_lints_future_nominal_auction_hallucination_and_relative_day_wording():
    payload={"snapshot":{
        "timestamp":"2026-09-15T01:46:00Z",
        "upcoming_auctions":[
            {"auction_date":"2026-09-15","term_key":"20-Year","instrument_class":"NOMINAL_COUPON"},
            {"auction_date":"2026-10-08","term_key":"10-Year","instrument_class":"NOMINAL_COUPON"},
        ],
    }}
    bad="Fresh auctions: 20Y auction today (Sep 15); pending 10Y auction Sep 17."
    v=llm.red_team_narrative_violations(bad,payload)
    assert any("today/tomorrow" in x for x in v)
    assert any("10-year on 2026-09-17" in x for x in v)
    good="Fresh nominal auction calendar: 20Y Sep 15; next supplied 10Y Oct 8."
    assert llm.red_team_narrative_violations(good,payload) == []


def test_temporal_claim_source_gate_rejects_july_source_for_august_claim():
    from dollar_dashboard.evidence import temporal_claim_source_mismatch
    claim="China extends its gold buying streak in August with a 20t purchase"
    source=("China gold market update: Strong official sector buying in July. "
            "The PBoC reported an addition of 20t of gold during July, the largest since late 2023. "
            "Chinese gold ETF inflows also continued in early August.")
    audit=temporal_claim_source_mismatch(claim,source)
    assert audit["mismatch"] is True
    assert audit["claim_months"] == [8]
    assert 7 in audit["source_support_months"]
    good=temporal_claim_source_mismatch(claim.replace("August","July"),source)
    assert good["mismatch"] is False


def test_verifier_temporal_gate_short_circuits_before_llm_network():
    result=llm.verify_claim_against_source(
        "China added about 20t of gold in August",
        "The PBoC reported an addition of 20t of gold during July.",
        "https://www.gold.org/example",
        base_url="http://does-not-matter", model="dummy", timeout_seconds=30,
    )
    assert result.startswith("INCONCLUSIVE")
    assert "temporal-consistency gate" in result


def test_legacy_supported_period_mismatch_is_quarantined_and_queue_downgraded(tmp_path, monkeypatch):
    from dollar_dashboard.storage import (
        save_verification_check, verification_check_summary_full,
        upsert_verification_queue, recent_verification_queue, update_verification_queue_check,
        verification_queue_summary_full, recent_quarantined_verification_checks,
    )
    monkeypatch.setenv("DOLLAR_DASHBOARD_DB", str(tmp_path / "temporal.sqlite"))
    claim="China added about 20t of gold in August"
    explanation="The WGC source states that the PBoC added 20t in July and calls July the largest month since late 2023."
    save_verification_check(claim,"Central-bank gold","https://www.gold.org/example","SUPPORTED",explanation,model="test",relevance_score=90,relevance_status="RELEVANT")
    upsert_verification_queue([{"priority":"P1","bucket":"Central-bank gold","claim":claim,"link":"https://example.com/headline"}])
    q=recent_verification_queue(10)[0]
    update_verification_queue_check(q["id"],candidate_url="https://www.gold.org/example",candidate_tier="RESEARCH",candidate_relevance=90,relevance_status="RELEVANT",verdict="SUPPORTED",explanation=explanation,status="CHECKED")
    # Persisted summary runs the migration/sync.
    active=verification_check_summary_full()
    assert active["total"] == 0
    quarantined=recent_quarantined_verification_checks(10)
    assert len(quarantined) == 1
    assert "temporal-consistency" in quarantined[0]["quarantine_reason"]
    qsum=verification_queue_summary_full()
    assert qsum["verdict_counts"].get("SUPPORTED",0) == 0
    assert qsum["verdict_counts"].get("INCONCLUSIVE",0) == 1


def test_temporal_gate_can_use_period_in_source_url_slug_when_explanation_is_wrong():
    from dollar_dashboard.evidence import temporal_claim_source_mismatch
    claim="China added about 20t of gold in August"
    source_meta=("https://www.gold.org/goldhub/gold-focus/2026/08/"
                 "china-gold-market-update-strong-official-sector-buying-july\n"
                 "The verifier incorrectly said this supports the August claim.")
    audit=temporal_claim_source_mismatch(claim,source_meta)
    assert audit["mismatch"] is True
    assert audit["source_support_months"] == [7]
