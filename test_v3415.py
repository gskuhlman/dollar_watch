from pathlib import Path

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION


def test_v3415_version_lineage_unchanged_score_model():
    assert __version__ == "3.4.25"
    assert APP_VERSION == "3.4.25"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.3"


def test_llm_does_not_predict_repo_event_from_thin_buffer_alone():
    src = Path("dollar_dashboard/llm.py").read_text(encoding="utf-8")
    assert "LIQUIDITY-BUFFER PREDICTION RULE" in src
    assert 'do NOT by themselves predict an impending repo event' in src
    assert '"classic setup"' in src
    assert 'actual repo/SOFR/tail/facility/basis evidence confirms stress' in src


def test_llm_keeps_supported_source_scope_narrow():
    src = Path("dollar_dashboard/llm.py").read_text(encoding="utf-8")
    assert "VERIFIED-SOURCE SCOPE RULE" in src
    assert "Country-specific evidence" in src
    assert "must not be generalized" in src
    assert "existence/metadata is not verification" in src


def test_llm_regime_direction_is_tendency_not_certainty():
    src = Path("dollar_dashboard/llm.py").read_text(encoding="utf-8")
    assert "REGIME-DIRECTION LANGUAGE RULE" in src
    assert "directional tendencies" in src
    assert "not deterministic outcomes" in src
