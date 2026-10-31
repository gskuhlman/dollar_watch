from __future__ import annotations

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION
from dollar_dashboard import llm


def _calendar_payload():
    return {"snapshot":{
        "timestamp":"2026-09-15T23:37:00Z",
        "upcoming_auctions":[
            {"auction_date":"2026-09-22","term_key":"2-Year","instrument_class":"NOMINAL_COUPON"},
            {"auction_date":"2026-09-23","term_key":"5-Year","instrument_class":"NOMINAL_COUPON"},
            {"auction_date":"2026-09-24","term_key":"7-Year","instrument_class":"NOMINAL_COUPON"},
        ],
    }}


def test_v3420_version_keeps_score_model_343():
    assert __version__ == "3.4.27"
    assert APP_VERSION == "3.4.27"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.4"


def test_mixed_shared_date_calendar_lint_checks_every_tenor():
    payload=_calendar_payload()
    bad="Near-term auctions: 2Y Sep 22; 2Y reopening + 5Y Sep 23; 7Y Sep 24."
    violations=llm.red_team_narrative_violations(bad,payload)
    assert any("2-year on 2026-09-23" in v for v in violations)


def test_explicit_frn_label_does_not_masquerade_as_nominal_2y():
    payload=_calendar_payload()
    good="Near-term auctions: 2Y Sep 22; 2Y FRN reopening + 5Y Sep 23; 7Y Sep 24."
    assert llm.red_team_narrative_violations(good,payload) == []


def test_clean_nominal_calendar_line_passes():
    payload=_calendar_payload()
    good="Near-term nominal auctions: 2Y Sep 22; 5Y Sep 23; 7Y Sep 24."
    assert llm.red_team_narrative_violations(good,payload) == []


def test_prompt_requires_same_record_for_month_specific_numeric_bundle():
    src=llm.analyze_with_local_llm.__code__.co_consts
    joined="\n".join(str(x) for x in src if isinstance(x,str))
    assert "VERIFIED-FACT COHERENCE RULE" in joined
    assert "same same-period verified record/source" in joined
    assert "MIXED-INSTRUMENT AUCTION RULE" in joined
