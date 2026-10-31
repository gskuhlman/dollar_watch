from __future__ import annotations

from dollar_dashboard import __version__
from dollar_dashboard.run_history import (APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION, build_fixed_horizon_context)


def _scores(v=10.0):
    return {"regimes":{"Managed dollar devaluation":v},"confidence":80.0}


def test_v3421_version_lineage_unchanged_score_model():
    assert __version__ == "3.4.27"
    assert APP_VERSION == "3.4.27"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.4"


def test_unavailable_horizon_has_human_reason():
    current={"timestamp":"2026-09-18T19:02:19Z","component_confidence":{}}
    ctx=build_fixed_horizon_context([],current,_scores())
    h=ctx["horizons"]["1D"]
    assert h["status"] == "UNAVAILABLE"
    assert "No stored snapshot" in h["status_reason"]
    assert "±8" in h["status_reason"]


def test_score_model_mismatch_has_human_reason():
    current={"timestamp":"2026-09-18T19:02:19Z","component_confidence":{}}
    ref={
        "timestamp":"2026-09-11T19:02:19Z",
        "scores":_scores(),
        "_schema_version":"3.4.1",
        "_score_model_version":"3.4.1",
        "component_confidence":{},
    }
    ctx=build_fixed_horizon_context([ref],current,_scores())
    h=ctx["horizons"]["7D"]
    assert h["status"] == "INCOMPARABLE_SCORE_MODEL"
    assert "3.4.1" in h["status_reason"]
    assert "3.4.4" in h["status_reason"]


def test_app_renders_na_not_none_for_horizon_cells():
    app=open("app.py",encoding="utf-8").read()
    assert 'row[label]=optional_number_text(d, decimals=1, signed=True)' in app
    assert '"Reason":h.get("status_reason") or "N/A"' in app
    assert "No comparable fixed-horizon reference is available yet" in app
