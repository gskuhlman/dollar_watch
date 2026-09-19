from __future__ import annotations

import pandas as pd

from dollar_dashboard import __version__
from dollar_dashboard import data, llm
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION
from dollar_dashboard.triggers import _next_auction
from dollar_dashboard.treasury_financing import _parse_fed_z1_html_series


def test_v3417_version_and_intentional_score_model_break():
    assert __version__ == "3.4.25"
    assert APP_VERSION == "3.4.25"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.3"


def test_realistic_fiscaldata_tips_and_frn_flags_override_note_type():
    raw = pd.DataFrame([
        {
            "security_type":"Note", "security_term":"9-Year 10-Month", "original_security_term":"10-Year",
            "inflation_index_security":"Yes", "floating_rate":"No", "auction_date":"2026-09-17",
        },
        {
            "security_type":"Note", "security_term":"2-Year", "original_security_term":"2-Year",
            "inflation_index_security":"No", "floating_rate":"Yes", "auction_date":"2026-09-23",
        },
        {
            "security_type":"Note", "security_term":"9-Year 11-Month", "original_security_term":"10-Year",
            "inflation_index_security":"No", "floating_rate":"No", "auction_date":"2026-09-09",
        },
    ])
    out = data._normalize_auction_frame(raw)
    assert out.iloc[0]["term_key"] == "10-Year TIPS"
    assert out.iloc[0]["instrument_class"] == "TIPS"
    assert out.iloc[1]["term_key"] == "2-Year FRN"
    assert out.iloc[1]["instrument_class"] == "FRN"
    assert out.iloc[2]["term_key"] == "10-Year"
    assert out.iloc[2]["instrument_class"] == "NOMINAL_COUPON"


def test_tips_reopening_cannot_replace_nominal_10y_in_stress_history():
    rows=[]
    # Three nominal 10Y observations establish a valid stress history.
    for d, btc in [("2026-09-09",2.70),("2026-08-12",2.50),("2026-07-09",2.45)]:
        rows.append({
            "security_type":"Note", "security_term":"10-Year", "original_security_term":"10-Year",
            "inflation_index_security":"No", "floating_rate":"No", "auction_date":d,
            "bid_to_cover_ratio":btc, "indirect_share_api":75, "dealer_share_api":12,
        })
    # Newer TIPS row is deliberately terrible. It must not become the nominal latest auction.
    rows.append({
        "security_type":"Note", "security_term":"10-Year", "original_security_term":"10-Year",
        "inflation_index_security":"Yes", "floating_rate":"No", "auction_date":"2026-09-17",
        "bid_to_cover_ratio":1.10, "indirect_share_api":20, "dealer_share_api":50,
    })
    norm=data._normalize_auction_frame(pd.DataFrame(rows))
    table, _ = data.summarize_auction_stress(norm)
    ten=table.loc[table["term"].eq("10-Year")].iloc[0]
    assert pd.Timestamp(ten["auction_date"]).date().isoformat() == "2026-09-09"
    assert float(ten["bid_to_cover"]) == 2.70


def test_upcoming_tips_is_not_nominal_replacement():
    snap={
        "upcoming_auctions":[
            {"auction_date":"2026-09-17", "term_key":"10-Year TIPS", "instrument_class":"TIPS"},
            {"auction_date":"2026-10-08", "term_key":"10-Year", "instrument_class":"NOMINAL_COUPON"},
        ]
    }
    nxt=_next_auction(snap,"10-Year",pd.Timestamp("2026-09-13T12:00:00Z"))
    assert pd.Timestamp(nxt).date().isoformat() == "2026-10-08"


def test_official_fed_z1_html_fallback_parser_converts_billions_to_millions():
    html='''
    <table><tr><th>Line</th><th>Description</th><th>Series</th><th>2026:Q1</th><th>2026:Q2</th></tr>
    <tr><td>37</td><td>Hedge funds</td><td>FA623061103</td><td>26.4</td><td>60.6</td></tr></table>
    '''
    s=_parse_fed_z1_html_series(html,"FA623061103")
    assert s.loc[pd.Timestamp("2026-01-01")] == 26400.0
    assert s.loc[pd.Timestamp("2026-04-01")] == 60600.0


def test_llm_percentile_window_rule_and_deterministic_lint():
    src=open(llm.__file__,encoding="utf-8").read()
    assert "record compensation" in src
    assert "supplied lookback" in src
    assert "red_team_narrative_violations" in src
    bad=("Structural supports: Fed bill accumulation as reserve management.\n"
         "The 10Y real yield is at the 100th percentile, so the market demands record compensation.")
    violations=llm.red_team_narrative_violations(bad)
    assert len(violations) == 2
    good=("Fed bill accumulation is reserve management and not structural dollar support.\n"
          "The 10Y real yield is at the top of the supplied 3-year lookback.")
    assert llm.red_team_narrative_violations(good) == []
