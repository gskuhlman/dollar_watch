import pandas as pd
from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION
from dollar_dashboard.buybacks import summarize_buybacks
from dollar_dashboard.llm import analyze_with_local_llm
import inspect

def test_version():
    assert __version__ == "3.4.8"
    assert APP_VERSION == "3.4.8"

def test_deterministic_long_end_buyback_ratios():
    now=pd.Timestamp.now(tz="UTC")
    rows=[]
    offered=[30e9,19e9,18e9,17e9,16e9,11.8e9]
    for i,o in enumerate(offered):
        rows.append({
            "operation_date": now-pd.Timedelta(days=i+1),
            "has_result": True,
            "maturity_bucket": "Nominal 10Y to 20Y",
            "security_type": "Nominal",
            "max_amount": 2e9,
            "total_offered": o,
            "total_accepted": 2e9,
        })
    out=summarize_buybacks(pd.DataFrame(rows), {"result_completeness_pct":100})
    assert out["long_end_completed_total_offered"] == 111.8e9
    assert out["long_end_completed_total_accepted"] == 12e9
    assert out["long_end_completed_capacity"] == 12e9
    assert out["long_end_offer_accept_ratio"] == 9.317
    assert out["long_end_offer_to_capacity_ratio"] == 9.317
    assert out["long_end_acceptance_vs_capacity"] == 1.0

def test_llm_semantic_guards_present():
    src=inspect.getsource(analyze_with_local_llm)
    assert "BUYBACK ARITHMETIC RULE" in src
    assert "FX INDEX ATTRIBUTION RULE" in src
    assert "PERCENTILE/VALUATION RULE" in src
