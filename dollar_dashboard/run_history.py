from __future__ import annotations

from datetime import datetime, timezone
import uuid
import pandas as pd

APP_VERSION='3.4.25'
SCHEMA_VERSION='3.4.1'
# Changes only when regime/component scoring math changes materially. App/layout/LLM
# releases may advance while this remains stable.
SCORE_MODEL_VERSION='3.4.3'

# Fixed analytical comparison horizons. These are deliberately independent of
# how often Streamlit/collector happens to run.
FIXED_HORIZONS = (
    ("1D", pd.DateOffset(days=1), pd.Timedelta(hours=8)),
    ("7D", pd.DateOffset(days=7), pd.Timedelta(days=1)),
    ("1M", pd.DateOffset(months=1), pd.Timedelta(days=3)),
    ("3M", pd.DateOffset(months=3), pd.Timedelta(days=7)),
    ("6M", pd.DateOffset(months=6), pd.Timedelta(days=14)),
    ("1Y", pd.DateOffset(years=1), pd.Timedelta(days=21)),
)


def _snapshot_time(s: dict | None) -> pd.Timestamp | None:
    if not s:
        return None
    raw = s.get("timestamp") or s.get("_captured_at") or (s.get("run_meta") or {}).get("captured_at")
    if not raw:
        return None
    try:
        ts = pd.Timestamp(raw)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts
    except Exception:
        return None


def fixed_horizon_query_windows(current_snapshot: dict) -> list[dict]:
    """Return bounded DB lookup windows for each analytical horizon."""
    cur_ts = _snapshot_time(current_snapshot) or pd.Timestamp.now(tz="UTC")
    out=[]
    for label, offset, tolerance in FIXED_HORIZONS:
        target=cur_ts-offset
        out.append({
            "label":label,
            "target_timestamp":target.isoformat(),
            "start_timestamp":(target-tolerance).isoformat(),
            "end_timestamp":(target+tolerance).isoformat(),
        })
    return out


# A replay uses only the input summaries saved in the historical snapshot.  Do not
# silently replace missing historical sources with today's values, overrides or news.
# Missing summaries would otherwise become zero scores in score(), creating fake deltas.
REPLAY_REQUIRED_INPUTS = (
    "market_summary", "fred_summary", "auction_stress_auto",
    "cftc_usd_downside_pressure", "fx_positioning_squeeze_risk",
    "cftc_summary", "tic_dedollarization_pressure",
    "tic_transaction_meta", "cofer_dedollarization_pressure",
    "fiscal_flow_stress_auto", "stablecoin_dollar_support_auto",
    "treasury_financing_meta", "official_policy_meta",
    "component_confidence", "data_confidence", "approved_verification_evidence",
    "overrides", "news_scores",
)


def replay_reference_scores(reference: dict, *, current_snapshot: dict, current_scores: dict) -> dict:
    """Re-score historical, captured inputs under the current model, without live fetches.

    The replay never updates the stored snapshot or its original score.  If an old
    snapshot predates a required input, refuse replay instead of treating it as zero.
    """
    from .scoring import score
    ts = _snapshot_time(reference)
    if ts is None:
        return {"ok": False, "reason": "Reference has no valid point-in-time timestamp."}
    missing = [key for key in REPLAY_REQUIRED_INPUTS if key not in reference or reference[key] is None]
    # A summary can legitimately be empty if its collector failed; in that case
    # component_confidence and historical data_health retain the failure evidence.
    if missing:
        return {"ok": False, "reason": "Historical snapshot lacks required replay inputs: " + ", ".join(missing)}
    if not isinstance(reference["overrides"], dict) or not isinstance(reference["news_scores"], dict):
        return {"ok": False, "reason": "Historical overrides/news scores are not stored in replayable format."}
    if not isinstance(reference["component_confidence"], dict) or not reference["component_confidence"]:
        return {"ok": False, "reason": "Historical component-confidence map is missing."}
    if not isinstance(reference["market_summary"], dict) or not isinstance(reference["fred_summary"], dict):
        return {"ok": False, "reason": "Historical market/FRED summaries are not replayable."}
    if not reference["market_summary"] or not reference["fred_summary"]:
        return {"ok": False, "reason": "Historical market/FRED summaries are empty."}
    # Normalized input generation evolved across releases.  Do not assert pristine
    # apples-to-apples source calculations when an old input schema differs.
    try:
        computed = score(reference, {"scores": reference["news_scores"]}, reference["overrides"], as_of=ts.to_pydatetime())
        if set(computed.get("regimes", {})) != set(current_scores.get("regimes", {})):
            return {"ok": False, "reason": "Historical replay returned a different regime taxonomy."}
    except Exception as exc:
        return {"ok": False, "reason": "Historical scoring replay failed: " + str(exc)[:240]}
    old_version = (reference.get("run_meta") or {}).get("score_model_version") or reference.get("_score_model_version")
    return {
        "ok": True, "scores": computed,
        "method": "REPLAY_CURRENT_MODEL_SAVED_INPUTS",
        "historical_input_model": old_version or "UNKNOWN",
        "limitations": (
            "Current score formula applied to saved point-in-time input summaries and original evidence/overrides; "
            "historical upstream collector calculations are not reconstructed, and missing source observations "
            "remain missing. Historical replay is an analytical estimate, not the old stored score."
        ),
    }


def build_fixed_horizon_context(history: list[dict], current_snapshot: dict, current_scores: dict, *, allow_historical_replay: bool = False) -> dict:
    """Build release/run-frequency-independent score comparisons.

    Each horizon uses the historical snapshot nearest the target date within a
    bounded tolerance. A missing or schema-incompatible reference is reported
    as unavailable rather than silently substituting an unrelated run.
    """
    cur_ts = _snapshot_time(current_snapshot) or pd.Timestamp.now(tz="UTC")
    current_regimes = current_scores.get("regimes", {}) or {}

    # Deduplicate repeated/manual runs with the same source timestamp. Keep the
    # newest captured record for each timestamp so reruns don't get extra weight.
    by_time: dict[pd.Timestamp, dict] = {}
    for snap in history or []:
        ts = _snapshot_time(snap)
        if ts is None or ts >= cur_ts:
            continue
        old = by_time.get(ts)
        if old is None:
            by_time[ts] = snap
        else:
            old_cap = pd.Timestamp(old.get("_captured_at") or old.get("timestamp"))
            new_cap = pd.Timestamp(snap.get("_captured_at") or snap.get("timestamp"))
            if new_cap > old_cap:
                by_time[ts] = snap

    candidates = [(ts, snap) for ts, snap in by_time.items()]
    out = {
        "current_timestamp": cur_ts.isoformat(),
        "current_scores": current_regimes,
        "horizons": {},
        "comparison_policy": "nearest historical snapshot to each fixed target within a bounded tolerance; no unrelated substitute",
    }

    for label, offset, tolerance in FIXED_HORIZONS:
        target = cur_ts - offset
        eligible = []
        for ts, snap in candidates:
            distance = abs(ts - target)
            if distance <= tolerance:
                eligible.append((distance, ts, snap))
        if not eligible:
            tol_hours = round(tolerance.total_seconds()/3600, 1)
            out["horizons"][label] = {
                "status": "UNAVAILABLE",
                "target_timestamp": target.isoformat(),
                "tolerance_hours": tol_hours,
                "status_reason": f"No stored snapshot exists within ±{tol_hours:g} hours of the fixed target.",
            }
            continue
        eligible.sort(key=lambda x: (x[0], -x[1].value))
        # The closest run can be a partial legacy record. Within the SAME fixed
        # time window, prefer the nearest reference whose score can actually be
        # compared or replayed; never widen a horizon to manufacture a delta.
        preselected_replay = None
        if allow_historical_replay and len(eligible) > 1:
            for candidate in eligible:
                _, _, trial = candidate
                trial_schema = trial.get("_schema_version") or (trial.get("run_meta") or {}).get("schema_version")
                trial_model = (trial.get("_score_model_version")
                               or (trial.get("run_meta") or {}).get("score_model_version")
                               or (SCHEMA_VERSION if trial_schema == SCHEMA_VERSION else None))
                old_regimes = (trial.get("scores") or {}).get("regimes") or {}
                if trial_schema not in (None, "LEGACY", SCHEMA_VERSION) or set(old_regimes) != set(current_regimes):
                    continue
                if trial_model in (None, "LEGACY", SCORE_MODEL_VERSION):
                    eligible.insert(0, eligible.pop(eligible.index(candidate)))
                    break
                attempt = replay_reference_scores(trial, current_snapshot=current_snapshot, current_scores=current_scores)
                if attempt.get("ok"):
                    eligible.insert(0, eligible.pop(eligible.index(candidate)))
                    preselected_replay = attempt
                    break
        _, ref_ts, ref = eligible[0]
        prev_scores = ref.get("scores", {}) or {}
        prev_regimes = prev_scores.get("regimes", {}) or {}
        ref_schema = ref.get("_schema_version") or (ref.get("run_meta") or {}).get("schema_version")
        ref_score_model = (
            ref.get("_score_model_version")
            or (ref.get("run_meta") or {}).get("score_model_version")
            # Backward compatibility: snapshots created under the current persisted
            # schema predate explicit score-model lineage, and all V3.4.1-V3.4.10
            # scoring changes were intentionally schema-compatible.
            or (SCHEMA_VERSION if ref_schema == SCHEMA_VERSION else None)
        )
        schema_comparable = (not ref_schema or ref_schema in {"LEGACY", SCHEMA_VERSION}) and set(prev_regimes) == set(current_regimes)
        if not schema_comparable:
            out["horizons"][label] = {
                "status": "INCOMPARABLE_SCHEMA",
                "target_timestamp": target.isoformat(),
                "reference_timestamp": ref_ts.isoformat(),
                "reference_schema": ref_schema,
                "current_schema": SCHEMA_VERSION,
                "reference_score_model": ref_score_model,
                "current_score_model": SCORE_MODEL_VERSION,
                "status_reason": f"A reference was found, but schema/regime keys are not comparable ({ref_schema or 'unknown'} vs {SCHEMA_VERSION}).",
            }
            continue
        replay_meta = preselected_replay
        if ref_score_model not in {None, "LEGACY", SCORE_MODEL_VERSION} and allow_historical_replay:
            if replay_meta is None:
                replay_meta = replay_reference_scores(ref, current_snapshot=current_snapshot, current_scores=current_scores)
            if replay_meta.get("ok"):
                prev_scores = replay_meta["scores"]
                prev_regimes = prev_scores["regimes"]
            else:
                out["horizons"][label] = {
                    "status": "REPLAY_INPUTS_INCOMPLETE",
                    "target_timestamp": target.isoformat(),
                    "reference_timestamp": ref_ts.isoformat(),
                    "reference_score_model": ref_score_model,
                    "current_score_model": SCORE_MODEL_VERSION,
                    "status_reason": replay_meta["reason"],
                }
                continue
        if ref_score_model not in {None, "LEGACY", SCORE_MODEL_VERSION} and not (replay_meta and replay_meta.get("ok")):
            out["horizons"][label] = {
                "status": "INCOMPARABLE_SCORE_MODEL",
                "target_timestamp": target.isoformat(),
                "reference_timestamp": ref_ts.isoformat(),
                "reference_schema": ref_schema,
                "current_schema": SCHEMA_VERSION,
                "reference_score_model": ref_score_model,
                "current_score_model": SCORE_MODEL_VERSION,
                "status_reason": f"A reference was found, but its score model {ref_score_model} differs from current {SCORE_MODEL_VERSION}.",
            }
            continue
        deltas = {}
        for name, val in current_regimes.items():
            old = prev_regimes.get(name)
            if old is not None:
                try:
                    deltas[name] = round(float(val) - float(old), 2)
                except Exception:
                    pass
        age = cur_ts - ref_ts
        cur_comp = current_snapshot.get("component_confidence", {}) or {}
        ref_comp = ref.get("component_confidence", {}) or {}
        comp_deltas = {}
        material_quality_changes = []
        for key in sorted(set(cur_comp) | set(ref_comp)):
            d = _delta(cur_comp.get(key), ref_comp.get(key))
            if d is None:
                continue
            comp_deltas[key] = d
            old_v = ref_comp.get(key)
            new_v = cur_comp.get(key)
            zero_transition = False
            try:
                zero_transition = (float(old_v) == 0.0) != (float(new_v) == 0.0)
            except Exception:
                pass
            if abs(float(d)) >= 20.0 or zero_transition:
                material_quality_changes.append({
                    "component": key, "delta_pp": d,
                    "reference_confidence": old_v, "current_confidence": new_v,
                })
        overall_conf_delta = _delta(current_scores.get("confidence"), prev_scores.get("confidence"))
        data_quality_affected = bool(material_quality_changes) or (overall_conf_delta is not None and abs(float(overall_conf_delta)) >= 5.0) or bool(replay_meta and replay_meta.get("ok"))
        out["horizons"][label] = {
            "status": "OK",
            "target_timestamp": target.isoformat(),
            "reference_timestamp": ref_ts.isoformat(),
            "actual_age_days": round(age.total_seconds()/86400, 2),
            "target_error_hours": round(abs(ref_ts-target).total_seconds()/3600, 1),
            "status_reason": (f"Current-model retrospective replay from saved historical inputs, {round(abs(ref_ts-target).total_seconds()/3600, 1):g} hours from target; see replay limitations."
                              if replay_meta and replay_meta.get("ok") else
                              f"Comparable snapshot found {round(abs(ref_ts-target).total_seconds()/3600, 1):g} hours from the fixed target."),
            "reference_run_id": ref.get("_run_id", ref.get("_id")),
            "reference_app_version": ref.get("_app_version", (ref.get("run_meta") or {}).get("app_version")),
            "reference_score_model": (SCORE_MODEL_VERSION if replay_meta and replay_meta.get("ok") else ref_score_model or SCORE_MODEL_VERSION),
            "current_score_model": SCORE_MODEL_VERSION,
            "reference_scores": prev_regimes,
            "comparison_method": (replay_meta or {}).get("method", "SAVED_SAME_MODEL_SCORE"),
            "reference_original_score_model": ref_score_model,
            "replay_limitations": (replay_meta or {}).get("limitations", ""),
            "regime_deltas": deltas,
            "confirmation_delta": _delta(current_scores.get("confirmation_index"), prev_scores.get("confirmation_index")),
            "early_warning_delta": _delta(current_scores.get("early_warning_index"), prev_scores.get("early_warning_index")),
            "confidence_delta": overall_conf_delta,
            "component_confidence_deltas": comp_deltas,
            "material_data_quality_changes": material_quality_changes,
            "data_quality_status": "DATA_QUALITY_AFFECTED" if data_quality_affected else "STABLE",
            "interpretation_guard": (
                "This horizon has material source-confidence changes or is a retrospective current-model replay of historical input summaries. These are not pure market/economic deltas; replayed values are analytical estimates."
                if data_quality_affected else
                "No material source-confidence/availability change detected across this horizon."
            ),
        }
    return out


def _delta(new, old):
    try:
        if new is None or old is None:
            return None
        return round(float(new)-float(old), 2)
    except Exception:
        return None


def fixed_horizon_reference(context: dict, label: str = "1D") -> dict | None:
    """Return a minimal previous-score object suitable for delta alerts."""
    row = (context.get("horizons", {}) or {}).get(label, {}) or {}
    if row.get("status") != "OK":
        return None
    return {
        "scores": {"regimes": row.get("reference_scores", {})},
        "_fixed_horizon": label,
        "_reference_timestamp": row.get("reference_timestamp"),
        "_score_model_version": row.get("reference_score_model"),
        "_data_quality_status": row.get("data_quality_status","STABLE"),
        "_material_data_quality_changes": row.get("material_data_quality_changes",[]),
        "_confidence_delta": row.get("confidence_delta"),
    }


def classify_snapshot_change(previous:dict|None,current:dict,current_scores:dict)->dict:
    if not previous:
        return {"kind":"BASELINE","items":[],"previous_run_id":None,"previous_schema":"NONE"}

    prev_app=previous.get('_app_version') or (previous.get('run_meta') or {}).get('app_version')
    prev_schema=previous.get('_schema_version') or (previous.get('run_meta') or {}).get('schema_version')
    prev_run=previous.get('_run_id') or (previous.get('run_meta') or {}).get('run_id') or previous.get('_id')
    prev_score_model=previous.get('_score_model_version') or (previous.get('run_meta') or {}).get('score_model_version') or (SCHEMA_VERSION if prev_schema == SCHEMA_VERSION else None)
    if not prev_app or not prev_schema:
        return {
            "kind":"LEGACY_BASELINE",
            "items":[{"kind":"LEGACY_BASELINE","detail":"Previous snapshot predates reliable app/schema lineage; regime/taxonomy deltas are not treated as market changes."}],
            "previous_run_id":prev_run,
            "previous_schema":prev_schema or 'LEGACY',
        }

    items=[]
    prev_scores=previous.get('scores',{}) or {}
    prev_reg=prev_scores.get('regimes',{}) or {}
    cur_reg=current_scores.get('regimes',{}) or {}
    if prev_schema != SCHEMA_VERSION or set(prev_reg)!=set(cur_reg):
        items.append({"kind":"MODEL_TAXONOMY_CHANGE","detail":f"schema {prev_schema} -> {SCHEMA_VERSION}; regime keys {len(prev_reg)} -> {len(cur_reg)}"})
    if prev_score_model not in {None, "LEGACY", SCORE_MODEL_VERSION}:
        items.append({"kind":"SCORE_MODEL_CHANGE","detail":f"score model {prev_score_model} -> {SCORE_MODEL_VERSION}; fixed-horizon score deltas across these versions are not analytically comparable"})

    prev_comp=(previous.get('component_confidence') or {})
    cur_comp=(current.get('component_confidence') or {})
    for k in sorted(set(cur_comp)-set(prev_comp)):
        items.append({"kind":"NEW_DATA_SOURCE","detail":k})

    # Operational audit only. Fixed-horizon analytical changes are calculated
    # separately; this identifies source refreshes/revisions between adjacent runs.
    for section in ['market_summary','fred_summary']:
        a=previous.get(section,{}) or {}; b=current.get(section,{}) or {}
        for key in set(a)&set(b):
            av=a.get(key,{}); bv=b.get(key,{})
            if isinstance(av,dict) and isinstance(bv,dict):
                old=av.get('last'); new=bv.get('last')
                try:
                    if old is not None and new is not None and float(old)!=float(new):
                        kind='MARKET_UPDATE' if section=='market_summary' else 'SOURCE_UPDATE_OR_REVISION'
                        items.append({"kind":kind,"detail":f"{section}:{key} {old} -> {new}"})
                except Exception:
                    pass
    kind='NO_MATERIAL_CHANGE' if not items else 'MIXED_CHANGES'
    return {"kind":kind,"items":items[:75],"previous_run_id":prev_run,"previous_schema":prev_schema,"current_schema":SCHEMA_VERSION,"previous_score_model":prev_score_model,"current_score_model":SCORE_MODEL_VERSION,"analytical_delta_policy":"FIXED_HORIZONS"}


def lineage(parent_run_id=None,run_kind='ANALYSIS')->dict:
    return {
        "run_id":str(uuid.uuid4()),
        "parent_run_id":parent_run_id,
        "app_version":APP_VERSION,
        "schema_version":SCHEMA_VERSION,
        "score_model_version":SCORE_MODEL_VERSION,
        "run_kind":run_kind,
        "captured_at":datetime.now(timezone.utc).isoformat(),
    }
