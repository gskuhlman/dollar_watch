"""Regression for ArrowInvalid when fixed-horizon fields mix floats and N/A."""
from pathlib import Path

import pandas as pd

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION
from dollar_dashboard.table_format import optional_number_text


def test_version_no_score_or_schema_bump():
    assert __version__ == APP_VERSION == "3.4.27"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.4"


def test_optional_number_formats_mixed_numeric_and_missing_as_strings():
    values = [0.79, None, 7.02, "N/A", float("nan"), float("inf"), "", 0, -2.4]
    result = [optional_number_text(v, decimals=2) for v in values]
    assert result == ["0.79", "N/A", "7.02", "N/A", "N/A", "N/A", "N/A", "0.00", "-2.40"]
    assert all(isinstance(value, str) for value in result)


def test_reference_table_numeric_fields_are_arrow_safe_display_columns():
    df = pd.DataFrame({
        "Actual age (days)": [optional_number_text(v) for v in (0.79, None, 7.02)],
        "Target error (hours)": [optional_number_text(v) for v in (5.2, None, 0.0)],
    })
    assert all(isinstance(value, str) for value in df.to_numpy().ravel())
    assert df["Actual age (days)"].tolist() == ["0.79", "N/A", "7.02"]
    try:
        import pyarrow as pa
    except ImportError:
        pass  # Runtime env installs Streamlit/PyArrow; unit tests remain dependency-light.
    else:
        arrow = pa.Table.from_pandas(df, preserve_index=False)
        assert arrow.schema.field("Actual age (days)").type == pa.string()
        assert arrow.schema.field("Target error (hours)").type == pa.string()


def test_horizon_delta_columns_display_consistent_strings_with_na():
    values = [None, 2.5, -0.9, 0.0]
    result = [optional_number_text(value, decimals=1, signed=True) for value in values]
    assert result == ["N/A", "+2.5", "-0.9", "+0.0"]
    assert all(isinstance(value, str) for value in result)


def test_executive_uses_arrow_safe_formats_for_both_tables():
    source = (Path(__file__).resolve().parent / "app.py").read_text(encoding="utf-8")
    assert 'row[label]=optional_number_text(d, decimals=1, signed=True)' in source
    assert '"Actual age (days)":optional_number_text(h.get("actual_age_days"), decimals=2)' in source
    assert '"Target error (hours)":optional_number_text(h.get("target_error_hours"), decimals=2)' in source
    assert '"Current":round(float(val),1)' in source  # current scores still numeric
