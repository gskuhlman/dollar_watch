from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION, build_fixed_horizon_context, fixed_horizon_reference
from dollar_dashboard.alerts import generate_alerts
import pandas as pd


def _snap(ts, score, *, schema=SCHEMA_VERSION, run_id=None):
    return {
        "timestamp": ts,
        "_captured_at": ts,
        "_run_id": run_id or ts,
        "_app_version": APP_VERSION,
        "_schema_version": schema,
        "_score_model_version": SCORE_MODEL_VERSION,
        "scores": {
            "regimes": {"FX positioning squeeze": score},
            "confirmation_index": score/2,
            "early_warning_index": score/3,
            "confidence": 80,
            "phase": "WATCH",
        },
    }


def test_fixed_horizon_ignores_immediately_previous_run():
    current={"timestamp":"2026-09-08T20:00:00Z"}
    scores={"regimes":{"FX positioning squeeze":60},"confirmation_index":30,"early_warning_index":20,"confidence":80}
    history=[
        _snap("2026-09-08T19:55:00Z",99,run_id="five-minutes-ago"),
        _snap("2026-09-07T20:00:00Z",50,run_id="one-day"),
        _snap("2026-09-01T20:00:00Z",40,run_id="one-week"),
    ]
    ctx=build_fixed_horizon_context(history,current,scores)
    assert ctx["horizons"]["1D"]["reference_run_id"] == "one-day"
    assert ctx["horizons"]["1D"]["regime_deltas"]["FX positioning squeeze"] == 10.0
    assert ctx["horizons"]["7D"]["regime_deltas"]["FX positioning squeeze"] == 20.0


def test_fixed_horizon_missing_history_is_na_not_bad_substitute():
    current={"timestamp":"2026-09-08T20:00:00Z"}
    scores={"regimes":{"FX positioning squeeze":60}}
    # This is 12 hours away from the 1D target, outside the ±8h rule.
    history=[_snap("2026-09-07T08:00:00Z",50)]
    ctx=build_fixed_horizon_context(history,current,scores)
    assert ctx["horizons"]["1D"]["status"] == "UNAVAILABLE"


def test_fixed_horizon_calendar_month_not_30_day_alias():
    current={"timestamp":"2026-09-30T20:00:00Z"}
    scores={"regimes":{"FX positioning squeeze":60}}
    history=[_snap("2026-08-30T20:00:00Z",45,run_id="calendar-month")]
    ctx=build_fixed_horizon_context(history,current,scores)
    assert ctx["horizons"]["1M"]["status"] == "OK"
    assert ctx["horizons"]["1M"]["reference_run_id"] == "calendar-month"
    assert ctx["horizons"]["1M"]["regime_deltas"]["FX positioning squeeze"] == 15.0


def test_regime_alert_uses_1d_reference_not_previous_run():
    current_scores={"regimes":{"FX positioning squeeze":60},"phase":"WATCH","confidence":80}
    previous=_snap("2026-09-08T19:55:00Z",61)
    one_day={"scores":{"regimes":{"FX positioning squeeze":40}}}
    empty=pd.DataFrame(columns=["Action","Trade $"])
    alerts=generate_alerts(current_scores,empty,previous,8,triggers=[],delta_reference=one_day,delta_label="1D")
    rc=[a for a in alerts if a.get("kind")=="regime_change"]
    assert len(rc)==1
    assert rc[0]["delta"] == 20.0
    assert rc[0]["delta_horizon"] == "1D"
    assert "over 1D" in rc[0]["message"]


def test_fixed_horizon_reference_minimal_alert_object():
    current={"timestamp":"2026-09-08T20:00:00Z"}
    scores={"regimes":{"FX positioning squeeze":60}}
    ctx=build_fixed_horizon_context([_snap("2026-09-07T20:00:00Z",50)],current,scores)
    ref=fixed_horizon_reference(ctx,"1D")
    assert ref["scores"]["regimes"]["FX positioning squeeze"] == 50
    assert ref["_fixed_horizon"] == "1D"


if __name__ == "__main__":
    test_fixed_horizon_ignores_immediately_previous_run()
    test_fixed_horizon_missing_history_is_na_not_bad_substitute()
    test_fixed_horizon_calendar_month_not_30_day_alias()
    test_regime_alert_uses_1d_reference_not_previous_run()
    test_fixed_horizon_reference_minimal_alert_object()
    print("v3.4.10 tests passed")
