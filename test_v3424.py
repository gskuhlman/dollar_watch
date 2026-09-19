"""Retrospective regime changes must never invent missing inputs or overwrite history."""
from datetime import datetime, timezone
from pathlib import Path

from dollar_dashboard import __version__
from dollar_dashboard.scoring import score
from dollar_dashboard.run_history import (
    APP_VERSION, SCORE_MODEL_VERSION, REPLAY_REQUIRED_INPUTS,
    build_fixed_horizon_context, replay_reference_scores,
)


def snapshot(ts="2026-09-11T19:30:00Z"):
    # A deliberately compact historical example with every required captured
    # input; optional collectors can have empty recorded summaries.
    s = {key: 0.0 for key in REPLAY_REQUIRED_INPUTS}
    s.update(
        timestamp=ts,
        market_summary={"DXY": {"last": 100.0}},
        fred_summary={"SOFR": {"last": 3.5}},
        component_confidence={"market": 100.0, "fred": 100.0},
        cftc_summary=[], tic_transaction_meta={}, treasury_financing_meta={},
        official_policy_meta={}, approved_verification_evidence=[],
        overrides={}, news_scores={}, data_confidence=75.0,
        _schema_version="3.4.1", _score_model_version="3.4.1",
    )
    return s


def test_v3424_lineage_and_no_score_model_bump():
    assert __version__ == APP_VERSION == "3.4.25"
    assert SCORE_MODEL_VERSION == "3.4.3"


def test_prior_model_is_replayed_using_its_own_inputs_and_clock():
    reference = snapshot()
    as_of = datetime(2026, 9, 11, 19, 30, tzinfo=timezone.utc)
    actual = score(reference, {"scores": {}}, {}, as_of=as_of)
    reference["scores"] = {"regimes": {k: 0 for k in actual["regimes"]}}  # old stored score must NOT be compared
    current = dict(reference, timestamp="2026-09-18T19:30:00Z")
    ctx = build_fixed_horizon_context([reference], current, actual, allow_historical_replay=True)
    h = ctx["horizons"]["7D"]
    assert h["status"] == "OK"
    assert h["comparison_method"] == "REPLAY_CURRENT_MODEL_SAVED_INPUTS"
    assert h["reference_original_score_model"] == "3.4.1"
    assert h["reference_score_model"] == "3.4.3"
    assert all(delta == 0.0 for delta in h["regime_deltas"].values())
    assert h["data_quality_status"] == "DATA_QUALITY_AFFECTED"
    assert all(val == 0 for val in reference["scores"]["regimes"].values())  # no mutation


def test_missing_historical_policy_or_override_cannot_be_backfilled_from_current():
    ref = snapshot()
    current = dict(ref, timestamp="2026-09-18T19:30:00Z")
    actual = score(ref, {"scores": {}}, {}, as_of=datetime(2026, 9, 11, tzinfo=timezone.utc))
    del ref["approved_verification_evidence"]
    result = replay_reference_scores(ref, current_snapshot=current, current_scores=actual)
    assert not result["ok"]
    assert "approved_verification_evidence" in result["reason"]
    ref["scores"] = actual
    h = build_fixed_horizon_context([ref], current, actual, allow_historical_replay=True)["horizons"]["7D"]
    assert h["status"] == "REPLAY_INPUTS_INCOMPLETE"
    assert "approved_verification_evidence" in h["status_reason"]


def test_missing_history_remains_na_no_month_from_two_weeks():
    ref = snapshot("2026-09-06T19:30:00Z")
    ref["scores"] = score(ref, {"scores": {}}, {}, as_of=datetime(2026, 9, 6, tzinfo=timezone.utc))
    cur = dict(ref, timestamp="2026-09-19T19:30:00Z")
    ctx = build_fixed_horizon_context([ref], cur, ref["scores"], allow_historical_replay=True)
    assert ctx["horizons"]["1M"]["status"] == "UNAVAILABLE"
    assert ctx["horizons"]["1Y"]["status"] == "UNAVAILABLE"


def test_time_aware_mof_scoring_is_historical_not_today():
    ref = snapshot("2026-09-11T19:30:00Z")
    ref["official_policy_meta"] = {
        "japan_fx_intervention": {
            "ok": True, "intervention_occurred": True,
            "period_start": "2026-07-30", "period_end": "2026-08-26",
            "direction": "UNKNOWN",
        }
    }
    historical = score(ref, {"scores": {}}, {}, as_of=datetime(2026, 9, 11, tzinfo=timezone.utc))
    late = score(ref, {"scores": {}}, {}, as_of=datetime(2027, 9, 11, tzinfo=timezone.utc))
    assert historical["regimes"]["FX positioning squeeze"] > late["regimes"]["FX positioning squeeze"]


def test_release_migrations_are_separate_from_persistent_runtime_state(monkeypatch):
    # On the user's installed system /data SHOULD exist and contain the live DB.
    # Archive exclusion is checked by the packaging verification, not by
    # asserting the installed runtime data directory is absent.
    root = Path(__file__).parent
    assert (root / "database" / "migrations").is_dir()
    from dollar_dashboard.paths import database_path, install_root
    monkeypatch.delenv("DOLLAR_DASHBOARD_DB", raising=False)
    monkeypatch.delenv("DOLLAR_WATCH_DATA_DIR", raising=False)
    assert database_path() == root / "data" / "dashboard.sqlite"
    assert install_root() == root
