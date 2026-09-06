from __future__ import annotations

import pandas as pd

ASSETS = [
    "T-bills / cash equivalents",
    "TIPS",
    "Gold",
    "Developed ex-US equities (unhedged)",
    "US real-asset / value equities",
    "CHF / defensive FX",
    "Bitcoin",
]

REGIME_TARGETS = {
    "Managed dollar devaluation": {
        "T-bills / cash equivalents": 15, "TIPS": 20, "Gold": 15,
        "Developed ex-US equities (unhedged)": 25, "US real-asset / value equities": 15,
        "CHF / defensive FX": 5, "Bitcoin": 5,
    },
    "Fiscal / inflation crisis": {
        "T-bills / cash equivalents": 20, "TIPS": 25, "Gold": 20,
        "Developed ex-US equities (unhedged)": 10, "US real-asset / value equities": 15,
        "CHF / defensive FX": 5, "Bitcoin": 5,
    },
    "Dollar funding squeeze": {
        "T-bills / cash equivalents": 45, "TIPS": 15, "Gold": 10,
        "Developed ex-US equities (unhedged)": 10, "US real-asset / value equities": 10,
        "CHF / defensive FX": 5, "Bitcoin": 5,
    },
    "Reserve-confidence crisis": {
        "T-bills / cash equivalents": 10, "TIPS": 20, "Gold": 25,
        "Developed ex-US equities (unhedged)": 20, "US real-asset / value equities": 10,
        "CHF / defensive FX": 10, "Bitcoin": 5,
    },
}


def recommend(regime_scores: dict[str, float], baseline: dict[str, float], portfolio_value: float, min_trade_pct: float = 2.0) -> tuple[pd.DataFrame, dict]:
    base = {a: float(baseline.get(a, 0)) for a in ASSETS}
    # Only scores above 35 influence allocation. The total crisis overlay is capped at 75%.
    raw = {r: max(0.0, (float(s)-35.0)/65.0) for r, s in regime_scores.items()}
    total_raw = sum(raw.values())
    overlay = min(0.75, 0.25 * total_raw)
    if total_raw > 0:
        weights = {r: v/total_raw for r, v in raw.items()}
    else:
        weights = {r: 0 for r in raw}

    crisis_target = {a: 0.0 for a in ASSETS}
    for regime, w in weights.items():
        tgt = REGIME_TARGETS[regime]
        for a in ASSETS:
            crisis_target[a] += w * tgt[a]

    rec = {}
    for a in ASSETS:
        target = (1-overlay)*base[a] + overlay*crisis_target[a] if total_raw > 0 else base[a]
        rec[a] = target
    # normalize numerical drift
    scale = 100.0 / sum(rec.values()) if sum(rec.values()) else 1
    rec = {k: v*scale for k,v in rec.items()}

    rows = []
    for a in ASSETS:
        delta = rec[a] - base[a]
        if delta >= min_trade_pct:
            action = "BUY"
        elif delta <= -min_trade_pct:
            action = "REDUCE"
        else:
            action = "HOLD"
        rows.append({
            "Asset": a,
            "Current %": round(base[a], 1),
            "Recommended %": round(rec[a], 1),
            "Change %": round(delta, 1),
            "Current $": round(portfolio_value*base[a]/100, 0),
            "Recommended $": round(portfolio_value*rec[a]/100, 0),
            "Trade $": round(portfolio_value*delta/100, 0),
            "Action": action,
        })
    df = pd.DataFrame(rows)
    meta = {"overlay_strength": overlay, "regime_weights": weights}
    return df, meta
