import pandas as pd

from dollar_dashboard.intelligence import parse_tic_mfh_text, summarize_tic, summarize_cftc_fx, summarize_stablecoins
from dollar_dashboard.scoring import score, DEFAULT_OVERRIDES
from dollar_dashboard.portfolio import recommend, scenario_stress_test, ASSETS


def test_tic_parser():
    txt = "x\nCountry\t2026-06\t2025-06\nJapan\t1116.7\t1154.8\nChina, Mainland\t633.4\t731.4\nGrand Total\t9299.0\t9093.6\nOf Which: Foreign Official\t3778.1\t3892.5\nNotes:\n"
    df = parse_tic_mfh_text(txt)
    assert len(df) == 8
    out, pressure, meta = summarize_tic(df)
    assert not out.empty
    assert 0 <= pressure <= 100


def test_cftc_summary():
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


def test_stablecoin_summary():
    assets=pd.DataFrame([
        {"name":"Tether","symbol":"USDT","peg_type":"peggedUSD","circulating_usd":180e9,"price":1.0},
        {"name":"USD Coin","symbol":"USDC","peg_type":"peggedUSD","circulating_usd":70e9,"price":1.0},
        {"name":"USD1","symbol":"USD1","peg_type":"peggedUSD","circulating_usd":4e9,"price":1.0},
    ])
    hist=pd.DataFrame({"date":pd.to_datetime(["2025-09-01","2026-06-01","2026-09-01"]),"market_cap_usd":[180e9,220e9,254e9]})
    focus, meta, support=summarize_stablecoins(assets,hist)
    assert meta["usd1_supply"] == 4e9
    assert 0 <= support <= 100


def test_v2_scoring_and_portfolio():
    snapshot={
      "market_summary":{"DXY":{"1m":-0.02,"3m":-0.05,"1y":-0.08},"Gold":{"3m":0.12},"Long Treasuries ETF":{"1m":-0.03},"EURUSD":{"3m":0.04},"USDJPY":{"3m":-0.04},"USDCHF":{"3m":-0.02}},
      "fred_summary":{"30Y Treasury":{"last":5.2,"3m_change":0.35},"10Y breakeven inflation":{"last":2.6,"3m_change":0.2},"10Y term premium":{"last":0.9,"3m_change":0.22},"VIX":{"last":20},"High-yield spread":{"last":3.6},"Financial Conditions Index":{"last":-0.1},"Central bank liquidity swaps (millions)":{"last":0,"1m_change":0},"Foreign custody UST YoY change (millions)":{"last":-180000},"Foreign official Treasury holdings (millions)":{"3m_change":-50000}},
      "auction_stress_auto":30,"cftc_usd_downside_pressure":65,"tic_dedollarization_pressure":45,"stablecoin_dollar_support_auto":55,"data_confidence":90,
    }
    ov={k:{"value":v,"note":""} for k,v in DEFAULT_OVERRIDES.items()}
    news={"scores":{"policy_devaluation":2,"external_dedollarization":2,"funding_stress":0,"dollar_support":1,"institutional_stress":0}}
    s=score(snapshot,news,ov)
    assert 0 <= s["early_warning_index"] <= 100
    assert 0 <= s["confirmation_index"] <= 100
    base={a:0 for a in ASSETS}
    base.update({"T-bills / cash equivalents":25,"TIPS":20,"Gold":15,"Developed ex-US equities (unhedged)":17.5,"US real-asset / value equities":10,"CHF / defensive FX":7.5,"Bitcoin":5})
    df,meta=recommend(s["regimes"],base,100000,market_summary=snapshot["market_summary"],confidence=s["confidence"])
    assert abs(df["Recommended %"].sum()-100)<0.2
    assert meta["one_way_turnover_pct"] <= 25.0001
    stress=scenario_stress_test(dict(zip(df["Asset"],df["Recommended %"])))
    assert len(stress)==4


if __name__ == "__main__":
    test_tic_parser(); test_cftc_summary(); test_stablecoin_summary(); test_v2_scoring_and_portfolio()
    print("v2 tests passed")
