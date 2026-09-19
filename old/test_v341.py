from dollar_dashboard.run_history import SCHEMA_VERSION
from dollar_dashboard.treasury_financing import Z1_FINANCING_SERIES

def test_v341_metadata_and_series():
    assert SCHEMA_VERSION == "3.4.1"
    assert Z1_FINANCING_SERIES["Nonfinancial corporate business"] == "NCBTSAQ027S"
    assert Z1_FINANCING_SERIES["Nonfinancial noncorporate business"] == "NNBGSAQ027S"

if __name__ == "__main__":
    test_v341_metadata_and_series()
    print("v3.4.1 metadata tests passed")
