from __future__ import annotations

import pandas as pd

from dollar_dashboard import __version__
from dollar_dashboard.intelligence import collect_tic_components_independent
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION, build_fixed_horizon_context
from dollar_dashboard import llm
from dollar_dashboard.alerts import generate_alerts


def _fred_tic_frame():
    idx=pd.to_datetime(["2026-05-31","2026-06-30"], utc=True)
    return pd.DataFrame({
        "Foreign Treasury holdings grand total (millions)":[9371100,9299000],
        "Foreign Treasury net transactions grand total (millions)":[10000,-22251],
        "Foreign LT Treasury valuation change grand total (millions)":[-5000,-12000],
        "Foreign official Treasury holdings (millions)":[3848000,3778100],
        "Foreign Treasury net transactions official (millions)":[-5000,-45400],
        "Foreign LT Treasury valuation change official (millions)":[-3000,-10000],
    },index=idx)


def test_v3419_version_and_score_model_bump():
    assert __version__ == "3.4.27"
    assert APP_VERSION == "3.4.27"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.4"


def test_tic_transaction_path_survives_direct_country_table_failure():
    def fail_country():
        raise RuntimeError("simulated direct TIC outage")
    out,status=collect_tic_components_independent(_fred_tic_frame(), fetch_major_func=fail_country)
    assert out["tic_meta"] == {}
    assert status["TIC country Treasury holdings"]["ok"] is False
    assert status["TIC Treasury transactions / valuation"]["ok"] is True
    assert out["tic_transaction_meta"]["foreign_official"]["net_transactions_mn"] == -45400
    assert out["tic_transaction_meta"]["grand_total"]["reconciles"] is True


def test_fixed_horizon_marks_material_data_quality_change():
    current={
        "timestamp":"2026-09-16T20:00:00Z",
        "component_confidence":{"tic":0.0,"tic_transactions":35.0,"fred":100.0},
    }
    current_scores={
        "regimes":{"Reserve-confidence crisis":27.0},
        "confidence":64.0,"confirmation_index":20.0,"early_warning_index":25.0,
    }
    history=[{
        "timestamp":"2026-09-15T20:00:00Z","_captured_at":"2026-09-15T20:00:00Z",
        "_schema_version":"3.4.1","_score_model_version":"3.4.4",
        "component_confidence":{"tic":35.0,"tic_transactions":35.0,"fred":100.0},
        "scores":{"regimes":{"Reserve-confidence crisis":29.0},"confidence":75.0,"confirmation_index":20.0,"early_warning_index":25.0},
    }]
    ctx=build_fixed_horizon_context(history,current,current_scores)
    row=ctx["horizons"]["1D"]
    assert row["status"] == "OK"
    assert row["data_quality_status"] == "DATA_QUALITY_AFFECTED"
    assert row["component_confidence_deltas"]["tic"] == -35.0
    assert any(x["component"]=="tic" for x in row["material_data_quality_changes"])
    assert "not pure market/economic deltas" in row["interpretation_guard"]


def test_tic_transaction_lint_blocks_active_sales_when_meta_missing():
    payload={"snapshot":{"tic_transaction_meta":{},"component_confidence":{"tic_transactions":0}}}
    text="Reserve confidence: foreign-official TIC net transactions were -$45.4B, confirming active selling."
    violations=llm.red_team_narrative_violations(text,payload)
    assert any("TIC active-transaction language" in x for x in violations)
    good_payload={"snapshot":{"tic_transaction_meta":{"foreign_official":{"net_transactions_mn":-45400}},"component_confidence":{"tic_transactions":35}}}
    assert not any("TIC active-transaction language" in x for x in llm.red_team_narrative_violations(text,good_payload))


def test_alerts_downgrade_fixed_horizon_regime_change_when_data_quality_affected():
    current={"regimes":{"Reserve-confidence crisis":20.0},"confidence":63.0,"phase":"WATCH/MIXED"}
    ref={
        "scores":{"regimes":{"Reserve-confidence crisis":30.0}},
        "_data_quality_status":"DATA_QUALITY_AFFECTED",
        "_material_data_quality_changes":[{"component":"tic","delta_pp":-35.0}],
        "_confidence_delta":-12.0,
    }
    alerts=generate_alerts(current,None,delta_reference=ref,score_delta_threshold=8.0,delta_label="1D")
    kinds={a["kind"] for a in alerts}
    assert "regime_change_data_quality_affected" in kinds
    assert "fixed_horizon_data_quality_change" in kinds
    msg=next(a["message"] for a in alerts if a["kind"]=="regime_change_data_quality_affected")
    assert "not interpret this as a pure market move" in msg
