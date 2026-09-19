import pandas as pd

from dollar_dashboard.intelligence import (
    parse_tic_mfh_text, summarize_tic, summarize_cftc_fx,
    summarize_stablecoins, summarize_fx_positioning_squeeze,
)
from dollar_dashboard.scoring import score, DEFAULT_OVERRIDES
from dollar_dashboard.portfolio import recommend, scenario_stress_test, ASSETS
from dollar_dashboard.evidence import effective_evidence_value, classify_source
from dollar_dashboard.triggers import evaluate_triggers
from dollar_dashboard.fiscal import summarize_fiscal
from dollar_dashboard.data import _normalize_auction_frame
from dollar_dashboard.llm import compact_previous_context
from dollar_dashboard.intelligence import period_last_date, build_data_health


def _unverified_overrides():
    return {k: {"value": v, "note": "", "source_url": "", "verification_status": "UNVERIFIED"} for k, v in DEFAULT_OVERRIDES.items()}


def test_tic_parser():
    txt = "x\nCountry\t2026-06\t2025-06\nJapan\t1116.7\t1154.8\nChina, Mainland\t633.4\t731.4\nGrand Total\t9299.0\t9093.6\nOf Which: Foreign Official\t3778.1\t3892.5\nNotes:\n"
    df = parse_tic_mfh_text(txt)
    assert len(df) == 8
    out, pressure, meta = summarize_tic(df)
    assert not out.empty
    assert 0 <= pressure <= 100


def test_cftc_summary_and_squeeze():
    dates = pd.date_range("2026-01-01", periods=8, freq="7D")
    rows=[]
    for i,d in enumerate(dates):
        rows.append({"report_date":d,"commodity_name":"EURO FX","contract_market_name":"EURO FX - CME","cftc_contract_market_code":"099741","open_interest_all":800000,
                     "lev_money_positions_long":100000+i*5000,"lev_money_positions_short":160000-i*2000,
                     "asset_mgr_positions_long":400000+i*3000,"asset_mgr_positions_short":180000-i*1000})
    df=pd.DataFrame(rows)
    out, p=summarize_cftc_fx(df)
    assert not out.empty
    assert 0 <= p <= 100
    crowded=pd.DataFrame([
        {"market":"Japanese Yen","leveraged_3y_percentile":5,"leveraged_weekly_change":-1000},
        {"market":"Euro FX","leveraged_3y_percentile":15,"leveraged_weekly_change":-500},
        {"market":"Swiss Franc","leveraged_3y_percentile":25,"leveraged_weekly_change":100},
    ])
    squeeze,reasons=summarize_fx_positioning_squeeze(crowded)
    assert squeeze > 70
    assert reasons


def test_stablecoin_summary_same_universe_bugfix():
    assets=pd.DataFrame([
        {"name":"Tether","symbol":"USDT","peg_type":"peggedUSD","circulating_usd":180e9,"price":1.0},
        {"name":"USD Coin","symbol":"USDC","peg_type":"peggedUSD","circulating_usd":70e9,"price":0.9988},
        {"name":"USD1","symbol":"USD1","peg_type":"peggedUSD","circulating_usd":4e9,"price":1.0},
        # Yield-bearing/tokenized Treasury products can intentionally trade above $1 NAV and must never be treated as depegged stablecoins.
        {"name":"Ondo U.S. Dollar Yield","symbol":"USDY","peg_type":"peggedUSD","circulating_usd":2e9,"price":1.142},
        {"name":"Hashnote US Yield Coin","symbol":"USYC","peg_type":"peggedUSD","circulating_usd":1.5e9,"price":1.08},
        # Tiny token with a large deviation must not create the >$1B alert or displayed max.
        {"name":"Tiny","symbol":"TINY","peg_type":"peggedUSD","circulating_usd":5e6,"price":0.80},
    ])
    hist=pd.DataFrame({"date":pd.to_datetime(["2025-09-01","2026-06-01","2026-09-01"]),"market_cap_usd":[180e9,220e9,254e9]})
    focus, meta, support=summarize_stablecoins(assets,hist)
    assert meta["usd1_supply"] == 4e9
    assert abs(meta["max_large_stablecoin_deviation_pct"] - 0.12) < 0.01
    assert meta["large_depeg_symbols"] == []
    assert meta["tokenized_rwa_supply"] == 3.5e9
    assert {x["symbol"] for x in meta["rwa_products"]} == {"USDY", "USYC"}
    assert 0 <= support <= 100


def test_auction_schema_normalization_legacy_and_current_aliases():
    raw=pd.DataFrame([{
        "record_date":"2026-08-31","cusip":"912TEST01","security_type":"Note","security_term":"10-Year",
        "original_security_term":"10-Year","announcemt_date":"2026-08-27","auction_date":"2026-08-31","issue_date":"2026-09-02",
        "reopening":"No","bid_to_cover_ratio":"2.55","comp_accepted":"42000000000","total_accepted_amt":"42500000000",
        "primary_dealer_accepted":"5000000000","direct_bidder_accepted":"3000000000","indirect_bidder_accepted":"34000000000",
    }])
    out=_normalize_auction_frame(raw)
    assert out.iloc[0]["term_key"] == "10-Year"
    assert str(out.iloc[0]["announcement_date"].date()) == "2026-08-27"
    assert abs(out.iloc[0]["dealer_share"] - (5/42*100)) < 0.01
    assert abs(out.iloc[0]["indirect_share"] - (34/42*100)) < 0.01


def test_future_source_date_is_flagged_not_extra_fresh():
    future=pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=2)
    health,conf=build_data_health({"Future source":{"ok":True,"weight":1.0,"last_date":future,"notes":"test"}})
    row=health.iloc[0]
    assert row["freshness"] == "source date ahead"
    assert row["age_days"] == 0
    assert row["confidence"] == 75
    assert "SOURCE_DATE_AHEAD" in row["data_hygiene_flag"]


def test_previous_run_context_has_true_deltas():
    prev={"_captured_at":"2026-09-05T12:00:00Z","scores":{"regimes":{"FX positioning squeeze":40}},"market_summary":{"DXY":{"last":100}}}
    cur_scores={"regimes":{"FX positioning squeeze":57.3}}
    ctx=compact_previous_context(prev,{"timestamp":"2026-09-06T12:00:00Z"},cur_scores)
    assert ctx["regime_delta_to_current"]["FX positioning squeeze"] == 17.3
    assert ctx["market_summary"]["DXY"]["last"] == 100


def test_evidence_verification_gate():
    assert classify_source("https://home.treasury.gov/x")["source_tier"] == "PRIMARY"
    assert effective_evidence_value(80, "UNVERIFIED", "https://home.treasury.gov/x") == 0
    assert effective_evidence_value(80, "VERIFIED", "") == 0
    assert effective_evidence_value(80, "VERIFIED", "https://home.treasury.gov/x") == 80
    assert 0 < effective_evidence_value(80, "VERIFIED", "https://reuters.com/x") < 80


def test_stale_confidence_applied_before_scoring():
    snapshot={
      "market_summary":{"DXY":{"last":99,"1m":0,"3m":0},"Gold":{"3m":0},"Long Treasuries ETF":{"1m":0},"EURUSD":{"3m":0},"USDJPY":{"3m":0},"USDCHF":{"3m":0}},
      "fred_summary":{},
      "tic_dedollarization_pressure":60,
      "cofer_dedollarization_pressure":50,
      "component_confidence":{"market":100,"fred":100,"auction":100,"cftc":100,"tic":35,"cofer":35,"fiscal":100,"stablecoin":100,"news":100},
      "data_confidence":80,
    }
    s=score(snapshot,{"scores":{}},_unverified_overrides())
    assert s["confidence_adjustments"]["TIC de-dollarization"]["effective"] == 21.0
    assert s["confidence_adjustments"]["COFER"]["effective"] == 17.5


def test_fiscal_summary():
    df=pd.DataFrame([{
        "record_date":"2026-08-31",
        "current_fytd_rcpt_amt":"4500000",
        "current_fytd_outly_amt":"6100000",
        "current_fytd_dfct_sur_amt":"-1600000",
        "prior_fytd_dfct_sur_amt":"-1400000",
    }])
    out=summarize_fiscal(df)
    assert out["fytd_deficit_mn"] == 1600000
    assert 0 <= out["stress_score"] <= 100


def test_cofer_period_freshness_date():
    assert str(period_last_date("2026-Q1").date()) == "2026-03-31"


def test_machine_triggers():
    weak10={"term":"10-Year","auction_date":"2026-09-09","bid_to_cover":2.30,"prior8_btc":2.50,"dealer_share_pct":16,"indirect_share_pct":62}
    weak30={"term":"30-Year","auction_date":"2026-09-10","bid_to_cover":2.20,"prior8_btc":2.40,"dealer_share_pct":16,"indirect_share_pct":60}
    snap={"auction_summary":[weak10,weak30],"fred_summary":{"10Y term premium":{"last":1.05},"10Y breakeven inflation":{"last":2.7},"Central bank liquidity swaps (millions)":{"last":0},"SOFR-IORB spread":{"last":0.02}},"market_summary":{"DXY":{"last":98,"3m":-0.01},"Gold":{"3m":0.10}},"cftc_usd_downside_pressure":20}
    trg=evaluate_triggers(snap,{})
    byid={x["id"]:x for x in trg}
    assert byid["weak_10y_30y_pair"]["status"] == "TRIGGERED"
    assert byid["fiscal_plus_inflation"]["status"] == "TRIGGERED"


def test_v21_scoring_and_portfolio():
    snapshot={
      "market_summary":{"DXY":{"last":99,"1m":-0.01,"3m":-0.05,"1y":-0.08},"Gold":{"3m":0.12},"Long Treasuries ETF":{"1m":-0.03},"EURUSD":{"3m":0.04},"USDJPY":{"3m":-0.04},"USDCHF":{"3m":-0.02}},
      "fred_summary":{"30Y Treasury":{"last":5.2,"3m_change":0.35},"10Y breakeven inflation":{"last":2.6,"3m_change":0.2},"10Y term premium":{"last":0.9,"3m_change":0.22},"10Y TIPS real yield":{"last":2.4},"VIX":{"last":20},"High-yield spread":{"last":3.6},"Financial Conditions Index":{"last":-0.1},"Central bank liquidity swaps (millions)":{"last":0,"1m_change":0},"Foreign custody UST YoY change (millions)":{"last":-180000},"Foreign official Treasury holdings (millions)":{"3m_change":-50000}},
      "auction_stress_auto":30,"cftc_usd_downside_pressure":65,"fx_positioning_squeeze_risk":40,"tic_dedollarization_pressure":45,"cofer_dedollarization_pressure":20,"fiscal_flow_stress_auto":35,"stablecoin_dollar_support_auto":55,"data_confidence":90,
      "component_confidence":{"market":100,"fred":100,"auction":100,"cftc":100,"tic":35,"cofer":35,"fiscal":90,"stablecoin":100,"news":100},
    }
    news={"scores":{"policy_devaluation":2,"external_dedollarization":2,"funding_stress":0,"dollar_support":1,"institutional_stress":0}}
    s=score(snapshot,news,_unverified_overrides())
    assert len(s["regimes"]) == 6
    assert 0 <= s["early_warning_index"] <= 100
    assert 0 <= s["confirmation_index"] <= 100
    base={a:0 for a in ASSETS}
    base.update({"T-bills / cash equivalents":25,"TIPS":20,"Gold":15,"Developed ex-US equities (unhedged)":17.5,"US real-asset / value equities":10,"CHF / defensive FX":7.5,"Bitcoin":5})
    df,meta=recommend(s["regimes"],base,100000,market_summary=snapshot["market_summary"],confidence=s["confidence"],min_trade_pct=1,min_position_pct=2,min_trade_dollars=1000,score_details=s)
    assert abs(df["Recommended %"].sum()-100)<0.2
    assert meta["one_way_turnover_pct"] <= 25.0001
    # No new token position should appear below 2%, and no actionable trade below $1,000.
    new_commodity=df[df["Asset"]=="Broad commodities / energy"].iloc[0]
    assert new_commodity["Recommended %"] == 0 or new_commodity["Recommended %"] >= 2
    actionable=df[df["Action"]!="HOLD"]
    assert actionable.empty or actionable["Trade $"].abs().min() >= 1000
    assert df["Why"].str.contains("Top risks:").all()
    assert not df["Why"].str.contains("highest absolute risk index is").any()
    stress=scenario_stress_test(dict(zip(df["Asset"],df["Recommended %"])))
    assert len(stress)==6


if __name__ == "__main__":
    test_tic_parser(); test_cftc_summary_and_squeeze(); test_stablecoin_summary_same_universe_bugfix()
    test_auction_schema_normalization_legacy_and_current_aliases(); test_future_source_date_is_flagged_not_extra_fresh(); test_previous_run_context_has_true_deltas()
    test_evidence_verification_gate(); test_stale_confidence_applied_before_scoring(); test_fiscal_summary()
    test_cofer_period_freshness_date(); test_machine_triggers(); test_v21_scoring_and_portfolio()
    print("v2.2 tests passed")
