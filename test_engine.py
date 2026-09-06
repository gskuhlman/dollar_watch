from dollar_dashboard.scoring import score, DEFAULT_OVERRIDES
from dollar_dashboard.portfolio import recommend


def fake_snapshot():
    return {
        "market_summary": {
            "DXY": {"1m": -0.02, "3m": -0.05},
            "Gold": {"1m": 0.04, "3m": 0.10},
            "Long Treasuries ETF": {"1m": -0.03},
            "Bitcoin": {"1m": 0.08},
            "EURUSD": {"3m": 0.04}, "USDJPY": {"3m": -0.02},
        },
        "fred_summary": {
            "10Y Treasury": {"last": 4.8},
            "30Y Treasury": {"last": 5.2, "3m_change": 0.35},
            "10Y breakeven inflation": {"last": 2.6, "3m_change": 0.15},
            "10Y TIPS real yield": {"last": 2.4},
            "VIX": {"last": 19}, "High-yield spread": {"last": 3.5},
        },
    }


def test_scores_and_portfolio():
    ov = {k: {"value": v, "note": ""} for k,v in DEFAULT_OVERRIDES.items()}
    news = {"scores": {"policy_devaluation": 2, "external_dedollarization": 3, "funding_stress": 0, "dollar_support": 1}}
    s = score(fake_snapshot(), news, ov)
    assert all(0 <= x <= 100 for x in s["regimes"].values())
    base = {"T-bills / cash equivalents":25,"TIPS":20,"Gold":15,"Developed ex-US equities (unhedged)":17.5,"US real-asset / value equities":10,"CHF / defensive FX":7.5,"Bitcoin":5}
    df, _ = recommend(s["regimes"], base, 100000)
    assert abs(df["Recommended %"].sum() - 100) < 0.2
    assert abs(df["Recommended $"].sum() - 100000) < 10


if __name__ == "__main__":
    test_scores_and_portfolio()
    print("engine test passed")
