from pathlib import Path

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION
from dollar_dashboard.scoring import score, DEFAULT_OVERRIDES


def _ovs():
    return {k:{"value":0,"verification_status":"UNVERIFIED","source_url":"","source_tier":"UNSOURCED"} for k in DEFAULT_OVERRIDES}


def _base_snapshot():
    return {
        "market_summary": {"DXY":{"last":99,"1m":0,"3m":0}},
        "fred_summary": {},
        "component_confidence": {
            "market":100,"fred":100,"cftc":90,"tic":35,"tic_transactions":35,
            "cofer":35,"fiscal":65,"stablecoin":100,"auction":90,"news":0,
            "buyback_schedule":100,"buyback_results":90,"buyback":90,
        },
        "auction_stress_auto":0,"cftc_usd_downside_pressure":30,"fx_positioning_squeeze_risk":70,
        "tic_dedollarization_pressure":0,"cofer_dedollarization_pressure":0,"fiscal_flow_stress_auto":0,
        "stablecoin_dollar_support_auto":20,"treasury_buyback_meta":{"intensity":20,"intensity_status":"KNOWN"},
        "approved_verification_evidence": [],
        "official_policy_meta": {},
        "offshore_usd_funding_meta": {"coverage":55.0,"reason":"true cross-currency basis unavailable"},
        "cftc_summary": [
            {"market":"Japanese Yen","report_date":"2026-09-01","leveraged_3y_percentile":15.0,"leveraged_net":-100000,"leveraged_weekly_change":-25000},
            {"market":"Dollar Index","report_date":"2026-09-01","leveraged_3y_percentile":80.0,"leveraged_net":10000,"leveraged_weekly_change":-1000},
        ],
    }


def _score():
    return score(_base_snapshot(), {"scores":{}}, _ovs())


def test_version():
    assert __version__ == "3.4.6"
    assert APP_VERSION == "3.4.6"


def test_cftc_four_date_lifecycle():
    u=_score()["observed_position_unwind"]
    assert u["latest_position_asof_date"] == "2026-09-01"
    assert u["latest_expected_publication_date"] == "2026-09-04"
    assert u["next_position_asof_date"] == "2026-09-08"
    assert u["next_expected_publication_date"] == "2026-09-11"
    assert u["expected_publication_date"] == "2026-09-11"


def test_partial_offshore_scope_language_gate():
    f=_score()["funding_observation_scope"]
    assert f["status"] == "PARTIAL_OFFSHORE"
    assert f["offshore_coverage_pct"] == 55.0
    assert "Do not describe global dollar funding as benign" in f["language_rule"]


def test_llm_prompt_contains_tga_and_funding_guardrails():
    text=(Path(__file__).parent/"dollar_dashboard"/"llm.py").read_text(encoding="utf-8")
    assert 'Do NOT call a TGA rebuild "prefunding future supply"' in text
    assert "PARTIAL_OFFSHORE" in text
    assert "latest_expected_publication_date" in text
