from pathlib import Path

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION


def test_v346_version():
    assert __version__ == "3.4.6"
    assert APP_VERSION == "3.4.6"


def test_mof_yen_buying_does_not_imply_treasury_sales():
    txt = (Path(__file__).parent / "dollar_dashboard" / "llm.py").read_text(encoding="utf-8")
    assert "does NOT by itself prove U.S. Treasury sales" in txt
    assert "Treasury-collateral liquidation" in txt
    assert "broad \"USD asset disposal.\"" in txt

