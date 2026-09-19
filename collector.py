"""Headless V3.4.11 collector for cron / Windows Task Scheduler.

Fetches all public feeds, scores the six risk regimes, calculates the guarded portfolio,
saves the snapshot, prints alerts, and optionally POSTs alerts to DOLLAR_DASHBOARD_WEBHOOK.
"""
from __future__ import annotations

import json
from pathlib import Path

from dollar_dashboard.pipeline import collect_live_bundle
from dollar_dashboard.news import classify_news
from dollar_dashboard.scoring import DEFAULT_OVERRIDES, score
from dollar_dashboard.portfolio import recommend
from dollar_dashboard.storage import get_overrides, get_setting, recent_snapshots, snapshots_for_fixed_horizons, save_snapshot, save_alerts, upsert_verification_queue, approved_verification_evidence
from dollar_dashboard.alerts import generate_alerts, send_webhook
from dollar_dashboard.triggers import evaluate_triggers
from dollar_dashboard.verification import systematic_policy_leads, verification_rows_from_news
from dollar_dashboard.official_policy import canonical_verification_leads
from dollar_dashboard.run_history import build_fixed_horizon_context, fixed_horizon_reference

ROOT = Path(__file__).resolve().parent
DEFAULT_SETTINGS = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))


def main():
    prior = recent_snapshots(1)
    prior = prior[0] if prior else None
    comparison_history = None
    bundle = collect_live_bundle()
    snap = bundle["snapshot"]
    news_df = bundle.get("news")
    news_class = classify_news(news_df)
    # V3.4.11: populate the research funnel even in headless scheduled runs. Standing probes
    # prevent a dark queue when RSS/news discovery is empty; headline rows are normalized
    # to primary-source verification families before persistence.
    queue_rows = verification_rows_from_news(news_df, max_rows=30) + systematic_policy_leads(max_rows=10) + canonical_verification_leads(bundle.get("official_policy",{}))
    if queue_rows:
        upsert_verification_queue(queue_rows)
    overrides = get_overrides(DEFAULT_OVERRIDES)
    snap["approved_verification_evidence"] = approved_verification_evidence(100)
    scores = score(snap, news_class, overrides)
    comparison_history = snapshots_for_fixed_horizons(snap)
    fixed_horizon_changes = build_fixed_horizon_context(comparison_history,snap,scores)
    one_day_reference = fixed_horizon_reference(fixed_horizon_changes,"1D")
    triggers = evaluate_triggers(snap, scores, previous_triggers=(prior or {}).get("machine_triggers",[]))
    portfolio_value = float(get_setting("portfolio_value", DEFAULT_SETTINGS["portfolio_value"]))
    baseline = get_setting("baseline_allocation", DEFAULT_SETTINGS["baseline_allocation"])
    min_trade = float(DEFAULT_SETTINGS.get("allocation_change_threshold_pct", 3.0))
    portfolio, meta = recommend(
        scores["regimes"], baseline, portfolio_value, min_trade_pct=min_trade,
        market_summary=snap.get("market_summary", {}), confidence=scores.get("confidence", 100),
        max_turnover_pct=float(DEFAULT_SETTINGS.get("max_turnover_pct", 25.0)),
        min_position_pct=float(DEFAULT_SETTINGS.get("min_position_pct", 2.0)),
        min_trade_dollars=float(DEFAULT_SETTINGS.get("min_trade_dollars", 1000.0)),
        score_details=scores, machine_triggers=triggers,
    )
    alerts = generate_alerts(scores, portfolio, prior, float(DEFAULT_SETTINGS.get("alert_threshold_points", 8)), triggers=triggers, delta_reference=one_day_reference, delta_label="1D")
    payload = {
        **snap,
        "scores": scores,
        "news_scores": news_class.get("scores", {}),
        "overrides": overrides,
        "machine_triggers": triggers,
        "portfolio": portfolio.to_dict(orient="records"),
        "portfolio_meta": meta,
        "alerts": alerts,
        "fixed_horizon_changes": fixed_horizon_changes,
    }
    rid = save_snapshot(payload, run_kind="SCHEDULED_COLLECTOR")
    save_alerts(alerts)
    print(f"Saved V3.4.11 snapshot #{rid} | phase={scores['phase']} | confidence={scores['confidence']:.0f}/100")
    print(f"Early warning={scores['early_warning_index']:.1f} | confirmation={scores['confirmation_index']:.1f}")
    one_day=((fixed_horizon_changes.get("horizons",{}) or {}).get("1D",{}) or {})
    for name, val in scores["regimes"].items():
        d=(one_day.get("regime_deltas",{}) or {}).get(name) if one_day.get("status")=="OK" else None
        delta = "" if d is None else f" ({float(d):+.1f} vs 1D)"
        print(f"{name}: {val:.1f}/100{delta}")
    trades = portfolio[portfolio["Action"] != "HOLD"]
    if trades.empty:
        print("Portfolio: HOLD — no guarded trade clears the minimum threshold.")
    else:
        print("Portfolio actions:")
        for _, r in trades.iterrows():
            print(f"  {r['Action']:6} {r['Asset']}: ${abs(r['Trade $']):,.0f} -> {r['Recommended %']:.1f}%")
    if alerts:
        print("Alerts:")
        for a in alerts: print(f"  [{a['severity']}] {a['message']}")
        sent, msg = send_webhook(alerts)
        if sent: print(msg)


if __name__ == "__main__":
    main()
