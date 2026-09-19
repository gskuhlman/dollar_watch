from pathlib import Path

from dollar_dashboard import __version__
from dollar_dashboard.llm import summarize_verification_records
from dollar_dashboard.run_history import (
    APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION,
    build_fixed_horizon_context, lineage,
)


def _snap(ts, score, *, score_model=None, schema=SCHEMA_VERSION):
    run_meta={"schema_version":schema,"app_version":"3.4.10"}
    if score_model is not None:
        run_meta["score_model_version"]=score_model
    return {
        "timestamp":ts,
        "_captured_at":ts,
        "_schema_version":schema,
        "run_meta":run_meta,
        "scores":{"regimes":{"FX positioning squeeze":score}},
    }


def test_v3411_version_and_score_model_lineage():
    assert __version__ == "3.4.25"
    assert APP_VERSION == "3.4.25"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.3"
    assert lineage()["score_model_version"] == "3.4.3"


def test_old_same_schema_snapshot_maps_to_pre_break_model_and_is_incomparable():
    current={"timestamp":"2026-09-08T20:00:00Z"}
    scores={"regimes":{"FX positioning squeeze":60}}
    ctx=build_fixed_horizon_context([_snap("2026-09-07T20:00:00Z",50)],current,scores)
    row=ctx["horizons"]["1D"]
    assert row["status"] == "INCOMPARABLE_SCORE_MODEL"
    assert row["reference_score_model"] == "3.4.1"
    assert row["current_score_model"] == "3.4.3"
    assert "regime_deltas" not in row


def test_different_score_model_blocks_fixed_horizon_delta():
    current={"timestamp":"2026-09-08T20:00:00Z"}
    scores={"regimes":{"FX positioning squeeze":60}}
    hist=[_snap("2026-09-07T20:00:00Z",10,score_model="9.9.9")]
    ctx=build_fixed_horizon_context(hist,current,scores)
    row=ctx["horizons"]["1D"]
    assert row["status"] == "INCOMPARABLE_SCORE_MODEL"
    assert "regime_deltas" not in row
    assert row["reference_score_model"] == "9.9.9"
    assert row["current_score_model"] == "3.4.3"


def test_verification_summary_is_authoritative_and_noncontradictory():
    rows=[
        {"claim":"stablecoin reserve role","verdict":"SUPPORTED","relevance_status":"RELEVANT","quarantine_status":"ACTIVE"},
        *[{"claim":f"lead {i}","verdict":"INCONCLUSIVE","relevance_status":"RELEVANT","quarantine_status":"ACTIVE"} for i in range(15)],
        {"claim":"bad claim","verdict":"CONTRADICTED","relevance_status":"RELEVANT","quarantine_status":"ACTIVE"},
    ]
    out=summarize_verification_records(rows)
    assert out["total"] == 17
    assert out["verdict_counts"] == {"SUPPORTED":1,"INCONCLUSIVE":15,"CONTRADICTED":1}
    assert out["supported_claims"] == ["stablecoin reserve role"]
    assert out["contradicted_claims"] == ["bad claim"]


def test_llm_has_new_accounting_and_neutrality_guardrails():
    src=Path("dollar_dashboard/llm.py").read_text(encoding="utf-8")
    assert "VERIFICATION COUNT RULE" in src
    assert "authoritative FULL-POPULATION database aggregates" in src
    assert "FED RESERVE-MANAGEMENT NEUTRALITY" in src
    assert "not by itself structural dollar support" in src
    assert "INFLATION LANGUAGE RULE" in src
    assert "INCOMPARABLE_SCORE_MODEL" in src


def test_app_passes_deterministic_verification_summaries():
    src=Path("app.py").read_text(encoding="utf-8")
    assert '"verification_check_summary":verification_check_summary_full()' in src
    assert '"verification_queue_state_summary":verification_queue_summary_full()' in src
    assert '"Reference score model"' in src

