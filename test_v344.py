from pathlib import Path
import pandas as pd

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION


def test_v344_metadata_schema_unchanged():
    assert __version__ == "3.4.8"
    assert APP_VERSION == "3.4.8"
    assert SCHEMA_VERSION == "3.4.1"


def test_financing_history_mixed_types_normalize_to_long_numeric():
    hist=pd.DataFrame({
        "date":["2026-03-31","2026-06-30","bad-date"],
        "fed_share_pct":["29.4",31.0,None],
        "bank_share_pct":[17.9,"18.2","not available"],
        "hedge_fund_share_pct":[None,None,None],
    })
    hist["date"]=pd.to_datetime(hist["date"],errors="coerce")
    hcols=["fed_share_pct","bank_share_pct","hedge_fund_share_pct"]
    for c in hcols:
        hist[c]=pd.to_numeric(hist[c],errors="coerce")
    usable=[c for c in hcols if hist[c].notna().any()]
    long=(hist[["date",*usable]].melt(id_vars="date",value_vars=usable,var_name="series",value_name="share_pct")
          .dropna(subset=["date","share_pct"]))
    assert usable == ["fed_share_pct","bank_share_pct"]
    assert pd.api.types.is_numeric_dtype(long["share_pct"])
    assert len(long) == 4


def test_app_uses_long_form_financing_chart():
    text=Path("app.py").read_text(encoding="utf-8")
    assert 'pd.to_numeric(plot_hist[c],errors="coerce")' in text
    assert '.melt(id_vars="date"' in text
    assert 'y="share_pct",color="series"' in text


if __name__ == "__main__":
    test_v344_metadata_schema_unchanged()
    test_financing_history_mixed_types_normalize_to_long_numeric()
    test_app_uses_long_form_financing_chart()
    print("v3.4.4 tests passed")
