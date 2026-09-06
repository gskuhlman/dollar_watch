from __future__ import annotations

import pandas as pd

ASSETS = [
    "T-bills / cash equivalents",
    "TIPS",
    "Gold",
    "Developed ex-US equities (unhedged)",
    "US real-asset / value equities",
    "Broad commodities / energy",
    "CHF / defensive FX",
    "Bitcoin",
]

REGIME_TARGETS = {
    "Managed dollar devaluation": {
        "T-bills / cash equivalents": 13, "TIPS": 18, "Gold": 15,
        "Developed ex-US equities (unhedged)": 24, "US real-asset / value equities": 14,
        "Broad commodities / energy": 7, "CHF / defensive FX": 5, "Bitcoin": 4,
    },
    "Fiscal / inflation crisis": {
        "T-bills / cash equivalents": 16, "TIPS": 24, "Gold": 20,
        "Developed ex-US equities (unhedged)": 9, "US real-asset / value equities": 12,
        "Broad commodities / energy": 10, "CHF / defensive FX": 5, "Bitcoin": 4,
    },
    "Dollar funding squeeze": {
        "T-bills / cash equivalents": 46, "TIPS": 14, "Gold": 9,
        "Developed ex-US equities (unhedged)": 8, "US real-asset / value equities": 9,
        "Broad commodities / energy": 4, "CHF / defensive FX": 6, "Bitcoin": 4,
    },
    "Reserve-confidence crisis": {
        "T-bills / cash equivalents": 8, "TIPS": 17, "Gold": 25,
        "Developed ex-US equities (unhedged)": 19, "US real-asset / value equities": 9,
        "Broad commodities / energy": 10, "CHF / defensive FX": 9, "Bitcoin": 3,
    },
}

# Illustrative one-year-equivalent stress shocks, not forecasts. Used to compare allocations consistently.
SCENARIO_SHOCKS = {
    "Managed dollar devaluation": {
        "T-bills / cash equivalents": 3, "TIPS": 6, "Gold": 12,
        "Developed ex-US equities (unhedged)": 11, "US real-asset / value equities": 8,
        "Broad commodities / energy": 9, "CHF / defensive FX": 8, "Bitcoin": 12,
    },
    "Fiscal / inflation crisis": {
        "T-bills / cash equivalents": 2, "TIPS": 7, "Gold": 16,
        "Developed ex-US equities (unhedged)": -4, "US real-asset / value equities": 2,
        "Broad commodities / energy": 13, "CHF / defensive FX": 5, "Bitcoin": 4,
    },
    "Dollar funding squeeze": {
        "T-bills / cash equivalents": 4, "TIPS": -4, "Gold": -8,
        "Developed ex-US equities (unhedged)": -15, "US real-asset / value equities": -12,
        "Broad commodities / energy": -12, "CHF / defensive FX": -3, "Bitcoin": -25,
    },
    "Reserve-confidence crisis": {
        "T-bills / cash equivalents": -1, "TIPS": 2, "Gold": 25,
        "Developed ex-US equities (unhedged)": 9, "US real-asset / value equities": -12,
        "Broad commodities / energy": 12, "CHF / defensive FX": 16, "Bitcoin": 8,
    },
}

PROXY = {
    "TIPS": ("TIPS ETF", "3m"),
    "Gold": ("Gold", "3m"),
    "Developed ex-US equities (unhedged)": ("Developed ex-US Equities", "3m"),
    "US real-asset / value equities": ("US Equities", "3m"),
    "Broad commodities / energy": ("Broad Commodities", "3m"),
    "CHF / defensive FX": ("Swiss Franc ETF", "3m"),
    "Bitcoin": ("Bitcoin", "1m"),
}

REVERSAL_TRIGGERS = {
    "T-bills / cash equivalents": "Reduce the defensive cash overweight if funding stress falls and higher-risk regimes retreat below WATCH.",
    "TIPS": "Reduce if inflation expectations and fiscal term premium fall materially while real yields remain attractive in nominal bonds.",
    "Gold": "Reduce if reserve/fiscal stress falls, real yields rise without credibility stress, and gold loses relative momentum.",
    "Developed ex-US equities (unhedged)": "Reduce if the dollar strengthens structurally or foreign growth/market risk deteriorates faster than U.S. risk.",
    "US real-asset / value equities": "Reduce if recession/funding stress dominates inflation and pricing-power benefits.",
    "Broad commodities / energy": "Reduce if inflation expectations fall, global demand weakens, or a dollar squeeze becomes dominant.",
    "CHF / defensive FX": "Reduce if dollar confidence improves and Swiss policy actively suppresses CHF appreciation.",
    "Bitcoin": "Reduce if liquidity/funding stress dominates or crypto begins behaving primarily as a high-beta risk asset.",
}


def _market_return(market_summary: dict | None, asset: str):
    if not market_summary or asset not in PROXY:
        return None
    series, window = PROXY[asset]
    try:
        v = market_summary.get(series, {}).get(window)
        return None if v is None else float(v)
    except Exception:
        return None


def _apply_chase_limiter(base: dict[str, float], rec: dict[str, float], market_summary: dict | None):
    notes = []
    adjusted = rec.copy()
    for asset in ASSETS:
        delta = adjusted[asset] - base[asset]
        if delta <= 0:
            continue
        r = _market_return(market_summary, asset)
        if r is None:
            continue
        factor = 1.0
        if asset == "Gold":
            factor = 0.5 if r > 0.15 else 1.0
            factor = 0.25 if r > 0.25 else factor
        elif asset == "Bitcoin":
            factor = 0.5 if r > 0.20 else 1.0
            factor = 0.25 if r > 0.40 else factor
        elif asset in ["Developed ex-US equities (unhedged)", "Broad commodities / energy", "CHF / defensive FX"]:
            factor = 0.65 if r > 0.15 else (0.8 if r > 0.10 else 1.0)
        if factor < 1.0:
            adjusted[asset] = base[asset] + delta * factor
            notes.append(f"Capped {asset} buy because its proxy has already risen {r*100:.1f}% over the monitored window.")
    # Send unallocated residual to short T-bills rather than forcing a chase into another risk hedge.
    residual = 100.0 - sum(adjusted.values())
    adjusted["T-bills / cash equivalents"] += residual
    return adjusted, notes


def recommend(
    regime_scores: dict[str, float], baseline: dict[str, float], portfolio_value: float,
    min_trade_pct: float = 2.0, market_summary: dict | None = None, confidence: float = 100.0,
    max_turnover_pct: float = 25.0,
) -> tuple[pd.DataFrame, dict]:
    base = {a: float(baseline.get(a, 0)) for a in ASSETS}
    total_base = sum(base.values())
    if total_base <= 0:
        raise ValueError("Baseline allocation must be greater than zero")
    base = {k: 100.0 * v / total_base for k, v in base.items()}

    raw = {r: max(0.0, (float(s) - 35.0) / 65.0) for r, s in regime_scores.items()}
    total_raw = sum(raw.values())
    confidence_scale = max(0.35, min(1.0, float(confidence) / 100.0))
    overlay = min(0.75, 0.25 * total_raw) * confidence_scale
    weights = {r: (v / total_raw if total_raw else 0.0) for r, v in raw.items()}

    crisis_target = {a: 0.0 for a in ASSETS}
    for regime, w in weights.items():
        target = REGIME_TARGETS[regime]
        for a in ASSETS:
            crisis_target[a] += w * target[a]

    rec = {}
    for a in ASSETS:
        rec[a] = (1 - overlay) * base[a] + overlay * crisis_target[a] if total_raw else base[a]
    scale = 100.0 / sum(rec.values())
    rec = {k: v * scale for k, v in rec.items()}

    rec, chase_notes = _apply_chase_limiter(base, rec, market_summary)

    # Cap one-way turnover to avoid large mechanical reallocations from one dashboard run.
    deltas = {a: rec[a] - base[a] for a in ASSETS}
    one_way_turnover = sum(abs(v) for v in deltas.values()) / 2.0
    if one_way_turnover > max_turnover_pct and one_way_turnover > 0:
        factor = max_turnover_pct / one_way_turnover
        rec = {a: base[a] + deltas[a] * factor for a in ASSETS}
        one_way_turnover = max_turnover_pct
        chase_notes.append(f"Scaled all trades to the {max_turnover_pct:.1f}% one-way turnover limit.")

    dominant = max(regime_scores.items(), key=lambda kv: kv[1])[0]
    rows = []
    for a in ASSETS:
        delta = rec[a] - base[a]
        if delta >= min_trade_pct:
            action = "BUY"
        elif delta <= -min_trade_pct:
            action = "REDUCE"
        else:
            action = "HOLD"
        role = {
            "T-bills / cash equivalents": "liquidity / dollar-squeeze defense",
            "TIPS": "inflation-linked real-rate defense",
            "Gold": "non-sovereign monetary hedge",
            "Developed ex-US equities (unhedged)": "foreign currency + productive assets",
            "US real-asset / value equities": "pricing power / domestic real assets",
            "Broad commodities / energy": "inflation / real-asset sensitivity",
            "CHF / defensive FX": "direct non-USD defensive currency",
            "Bitcoin": "small convex monetary/liquidity hedge",
        }[a]
        rows.append({
            "Asset": a,
            "Current %": round(base[a], 1),
            "Recommended %": round(rec[a], 1),
            "Change %": round(delta, 1),
            "Current $": round(portfolio_value * base[a] / 100, 0),
            "Recommended $": round(portfolio_value * rec[a] / 100, 0),
            "Trade $": round(portfolio_value * delta / 100, 0),
            "Action": action,
            "Why": f"{role}; dominant modeled regime is {dominant}.",
            "Reversal trigger": REVERSAL_TRIGGERS[a],
        })
    df = pd.DataFrame(rows)
    meta = {
        "overlay_strength": overlay,
        "regime_weights": weights,
        "one_way_turnover_pct": one_way_turnover,
        "confidence_scale": confidence_scale,
        "chase_notes": chase_notes,
        "dominant_regime": dominant,
    }
    return df, meta


def scenario_stress_test(allocation: dict[str, float], portfolio_value: float = 100000.0) -> pd.DataFrame:
    total = sum(float(allocation.get(a, 0)) for a in ASSETS)
    if total <= 0:
        return pd.DataFrame()
    weights = {a: float(allocation.get(a, 0)) / total for a in ASSETS}
    rows = []
    for scenario, shocks in SCENARIO_SHOCKS.items():
        ret = sum(weights[a] * shocks[a] for a in ASSETS)
        rows.append({
            "Scenario": scenario,
            "Illustrative portfolio return %": round(ret, 1),
            "Illustrative P/L $": round(portfolio_value * ret / 100.0, 0),
        })
    return pd.DataFrame(rows)
