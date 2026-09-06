from __future__ import annotations

import os
import requests


def generate_alerts(current_scores: dict, portfolio_df, previous: dict | None = None, score_delta_threshold: float = 8.0) -> list[dict]:
    alerts: list[dict] = []
    prev_scores = (previous or {}).get("scores", {}) if previous else {}
    prev_regimes = prev_scores.get("regimes", {})

    for name, val in current_scores.get("regimes", {}).items():
        old = prev_regimes.get(name)
        if old is not None:
            delta = float(val) - float(old)
            if abs(delta) >= score_delta_threshold:
                alerts.append({
                    "severity": "HIGH" if val >= 70 or delta >= 15 else "WATCH",
                    "kind": "regime_change",
                    "message": f"{name} changed {delta:+.1f} points to {val:.1f}/100.",
                    "regime": name, "score": val, "delta": delta,
                })
        if float(val) >= 70:
            alerts.append({
                "severity": "HIGH" if float(val) < 85 else "ACUTE",
                "kind": "regime_level",
                "message": f"{name} is {val:.1f}/100.",
                "regime": name, "score": val,
            })

    phase = current_scores.get("phase")
    old_phase = prev_scores.get("phase") if previous else None
    if phase and old_phase and phase != old_phase:
        alerts.append({"severity": "WATCH", "kind": "phase_change", "message": f"Early-warning phase changed from {old_phase} to {phase}."})

    if current_scores.get("confidence", 100) < 60:
        alerts.append({"severity": "WATCH", "kind": "data_quality", "message": f"Data confidence is only {current_scores.get('confidence',0):.0f}/100; hard recommendations should be discounted."})

    if portfolio_df is not None and not portfolio_df.empty:
        trades = portfolio_df[portfolio_df["Action"] != "HOLD"]
        for _, r in trades.iterrows():
            if abs(float(r.get("Trade $", 0))) >= 5000:
                alerts.append({
                    "severity": "ACTION", "kind": "portfolio",
                    "message": f"{r['Action']} {r['Asset']} ${abs(float(r['Trade $'])):,.0f} to target {float(r['Recommended %']):.1f}%.",
                })
    # Deduplicate exact messages.
    seen=set(); out=[]
    for a in alerts:
        if a["message"] not in seen:
            seen.add(a["message"]); out.append(a)
    return out


def send_webhook(alerts: list[dict], url: str | None = None) -> tuple[bool, str]:
    url = url or os.getenv("DOLLAR_DASHBOARD_WEBHOOK", "")
    if not url or not alerts:
        return False, "No webhook configured or no alerts."
    try:
        r = requests.post(url, json={"alerts": alerts}, timeout=12)
        r.raise_for_status()
        return True, f"Webhook delivered ({r.status_code})."
    except Exception as exc:
        return False, str(exc)
