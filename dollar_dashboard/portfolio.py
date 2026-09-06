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
    "Fiscal / Treasury supply stress": {
        "T-bills / cash equivalents": 28, "TIPS": 18, "Gold": 12,
        "Developed ex-US equities (unhedged)": 12, "US real-asset / value equities": 12,
        "Broad commodities / energy": 5, "CHF / defensive FX": 8, "Bitcoin": 5,
    },
    "Inflation / monetary debasement": {
        "T-bills / cash equivalents": 14, "TIPS": 25, "Gold": 20,
        "Developed ex-US equities (unhedged)": 10, "US real-asset / value equities": 12,
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
    "FX positioning squeeze": {
        "T-bills / cash equivalents": 32, "TIPS": 18, "Gold": 12,
        "Developed ex-US equities (unhedged)": 12, "US real-asset / value equities": 10,
        "Broad commodities / energy": 4, "CHF / defensive FX": 8, "Bitcoin": 4,
    },
}

SCENARIO_SHOCKS = {
    "Managed dollar devaluation": {
        "T-bills / cash equivalents": 3, "TIPS": 6, "Gold": 12,
        "Developed ex-US equities (unhedged)": 11, "US real-asset / value equities": 8,
        "Broad commodities / energy": 9, "CHF / defensive FX": 8, "Bitcoin": 12,
    },
    "Fiscal / Treasury supply stress": {
        "T-bills / cash equivalents": 4, "TIPS": -2, "Gold": 5,
        "Developed ex-US equities (unhedged)": -5, "US real-asset / value equities": -4,
        "Broad commodities / energy": 1, "CHF / defensive FX": 4, "Bitcoin": -5,
    },
    "Inflation / monetary debasement": {
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
    "FX positioning squeeze": {
        "T-bills / cash equivalents": 3, "TIPS": 2, "Gold": 4,
        "Developed ex-US equities (unhedged)": 5, "US real-asset / value equities": -2,
        "Broad commodities / energy": 1, "CHF / defensive FX": 8, "Bitcoin": -2,
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

FUNDING_HEDGE_CLASS = {
    "T-bills / cash equivalents":"DIRECT HEDGE",
    "TIPS":"USD-DENOMINATED / RATE-SENSITIVE",
    "Gold":"CONDITIONAL / UNRELIABLE",
    "Developed ex-US equities (unhedged)":"VULNERABLE",
    "US real-asset / value equities":"VULNERABLE",
    "Broad commodities / energy":"VULNERABLE",
    "CHF / defensive FX":"CONDITIONAL / UNRELIABLE",
    "Bitcoin":"VULNERABLE",
}

REVERSAL_TRIGGERS = {
    "T-bills / cash equivalents": "Reduce defensive cash only after repo/funding conditions are benign and fiscal/reserve regimes retreat.",
    "TIPS": "Reduce if breakevens fall, term premium normalizes, and fiscal/inflation regimes retreat.",
    "Gold": "Reduce if reserve/fiscal stress falls, DXY strengthens, central-bank demand cools, and gold loses relative momentum.",
    "Developed ex-US equities (unhedged)": "Reduce if the dollar strengthens structurally or foreign growth deteriorates faster than U.S. risk.",
    "US real-asset / value equities": "Reduce if recession/funding stress dominates inflation/pricing-power benefits.",
    "Broad commodities / energy": "Reduce if inflation expectations fall, global demand weakens, or a dollar squeeze becomes dominant.",
    "CHF / defensive FX": "Reduce if dollar confidence improves or Swiss policy actively suppresses CHF appreciation.",
    "Bitcoin": "Reduce if liquidity stress dominates or BTC again behaves as high-beta risk while gold performs as the monetary hedge.",
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
    adjusted["T-bills / cash equivalents"] += 100.0 - sum(adjusted.values())
    return adjusted, notes


def _remove_token_positions(base: dict[str,float], rec: dict[str,float], min_position_pct: float) -> tuple[dict[str,float], list[str]]:
    notes=[]; out=rec.copy()
    for a in ASSETS:
        if a == "T-bills / cash equivalents":
            continue
        # Do not initiate a de-minimis position. Existing meaningful positions may drift below the threshold.
        if base[a] < min_position_pct and out[a] < min_position_pct:
            if out[a] > 0.01:
                notes.append(f"Suppressed token {a} target of {out[a]:.1f}% (<{min_position_pct:.1f}% minimum position).")
            out[a]=0.0
    out["T-bills / cash equivalents"] += 100.0-sum(out.values())
    return out, notes



_DRIVER_KEY = {
    "Managed dollar devaluation": "managed_devaluation",
    "Fiscal / Treasury supply stress": "fiscal_treasury",
    "Inflation / monetary debasement": "inflation_debasement",
    "Dollar funding squeeze": "dollar_squeeze",
    "Reserve-confidence crisis": "reserve_confidence",
    "FX positioning squeeze": "fx_positioning_squeeze",
}


def _asset_rationale(asset: str, action: str, regime_scores: dict[str, float], score_details: dict | None,
                     market_summary: dict | None, delta: float, actionable_pct: float) -> str:
    ranked = sorted(regime_scores.items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[:2]
    bits = [f"{name} {value:.0f}/100" for name, value in top]
    drivers = []
    if score_details:
        all_drivers = score_details.get("drivers", {}) or {}
        for name, _value in top:
            for d in all_drivers.get(_DRIVER_KEY.get(name, ""), [])[:2]:
                if d not in drivers:
                    drivers.append(str(d))
    if action == "HOLD":
        decision = f"No modeled shift clears the {actionable_pct:.1f}pp actionable threshold"
    else:
        decision = f"Model target changes by {delta:+.1f}pp after confidence, turnover and anti-chasing guardrails"
    asset_context = {
        "T-bills / cash equivalents": "Liquidity/optionality protects a dollar-funding squeeze and keeps dry powder for later confirmation.",
        "TIPS": "Inflation linkage helps if fiscal stress broadens into realized/expected inflation without taking full long-nominal duration risk.",
        "Gold": "Non-sovereign monetary hedge is most useful for reserve-confidence/debasement risk but can be expensive after a large run.",
        "Developed ex-US equities (unhedged)": "Combines productive foreign assets with non-USD currency exposure; vulnerable in a global funding squeeze.",
        "US real-asset / value equities": "Pricing power/real assets help moderate inflation but can suffer if rates or credit stress dominate.",
        "Broad commodities / energy": "Useful mainly when inflation/debasement or real-asset scarcity is confirmed; poor hedge in a funding squeeze.",
        "CHF / defensive FX": "Direct non-USD defensive currency exposure; SNB reaction and short-covering can dominate short-term moves.",
        "Bitcoin": "Small convex monetary hedge, but behaves like high-beta liquidity risk in many funding shocks.",
    }[asset]
    evidence = f" Active evidence: {'; '.join(drivers)}." if drivers else " No high-confidence causal driver beyond the regime indices is active."
    return f"{decision}. Top risks: {', '.join(bits)}. {asset_context}{evidence}"

def _apply_machine_precommitments(rec: dict[str,float], machine_triggers: list[dict] | None) -> tuple[dict[str,float], list[str]]:
    """Apply only fresh TRIGGERED machine pre-commitments; aging/pending signals never trade.

    The weak-auction response is conditional on the trigger's stress_flavor so real-yield
    fiscal stress does not mechanically add TIPS duration.
    """
    out=rec.copy(); notes=[]
    by={str(t.get("id")):t for t in (machine_triggers or [])}
    funding=by.get("repo_or_swap_stress")
    if funding and funding.get("status")=="TRIGGERED":
        # A dollar-liquidity event is the opposite of a non-USD risk-on signal.  Move
        # explicitly toward bills and away from the two most reliable funding-shock losers.
        cut_btc=min(2.0,out["Bitcoin"])
        cut_exus=min(2.0,out["Developed ex-US equities (unhedged)"])
        out["Bitcoin"]-=cut_btc
        out["Developed ex-US equities (unhedged)"]-=cut_exus
        out["T-bills / cash equivalents"]+=cut_btc+cut_exus
        notes.append(f"Funding-stress pre-commitment applied: +{cut_btc+cut_exus:.1f}pp T-bills funded from BTC/ex-US. Large swap/FIMA draws are dollar-liquidity stress, never a reason to add non-USD exposure.")

    weak=by.get("weak_10y_30y_pair")
    if weak and weak.get("status")=="TRIGGERED":
        flavor=weak.get("stress_flavor")
        if flavor=="INFLATIONARY_FISCAL":
            out["T-bills / cash equivalents"]-=3.0
            out["TIPS"]+=2.0
            out["Gold"]+=1.0
            notes.append("Fresh weak 10Y/30Y auctions + elevated breakevens: pre-commitment applied (+2pp TIPS, +1pp gold, -3pp T-bills).")
        else:
            # Anchored inflation + rising real/term yields: avoid adding TIPS duration.
            out["T-bills / cash equivalents"]+=2.0
            out["Gold"]+=1.0
            out["TIPS"]-=1.0
            out["US real-asset / value equities"]-=1.0
            out["Developed ex-US equities (unhedged)"]-=1.0
            notes.append("Fresh weak 10Y/30Y auctions with anchored breakevens: real-yield fiscal pre-commitment applied (+2pp T-bills, +1pp gold; -1pp each TIPS/US real-assets/ex-US).")
    # Normalize for defensive robustness if a baseline is unusual.
    for a in ASSETS:
        out[a]=max(0.0,float(out[a]))
    total=sum(out.values())
    if total>0:
        out={a:100.0*out[a]/total for a in ASSETS}
    return out,notes


def recommend(
    regime_scores: dict[str, float], baseline: dict[str, float], portfolio_value: float,
    min_trade_pct: float = 2.0, market_summary: dict | None = None, confidence: float = 100.0,
    max_turnover_pct: float = 25.0, min_position_pct: float = 2.0, min_trade_dollars: float = 1000.0,
    score_details: dict | None = None, machine_triggers: list[dict] | None = None,
) -> tuple[pd.DataFrame, dict]:
    base = {a: float(baseline.get(a, 0)) for a in ASSETS}
    total_base = sum(base.values())
    if total_base <= 0:
        raise ValueError("Baseline allocation must be greater than zero")
    base = {k: 100.0 * v / total_base for k, v in base.items()}

    # Scores are risk indices, not probabilities. Only risk above 35 creates an overlay.
    raw = {r: max(0.0, (float(s) - 35.0) / 65.0) for r, s in regime_scores.items() if r in REGIME_TARGETS}
    total_raw = sum(raw.values())
    confidence_scale = max(0.35, min(1.0, float(confidence) / 100.0))
    overlay = min(0.75, 0.22 * total_raw) * confidence_scale
    weights = {r: (v / total_raw if total_raw else 0.0) for r, v in raw.items()}

    crisis_target = {a: 0.0 for a in ASSETS}
    for regime, w in weights.items():
        target = REGIME_TARGETS[regime]
        for a in ASSETS:
            crisis_target[a] += w * target[a]

    rec = {a: ((1-overlay)*base[a] + overlay*crisis_target[a]) if total_raw else base[a] for a in ASSETS}
    rec = {k: v * 100.0 / sum(rec.values()) for k, v in rec.items()}
    rec, chase_notes = _apply_chase_limiter(base, rec, market_summary)
    rec, trigger_notes = _apply_machine_precommitments(rec, machine_triggers)
    chase_notes.extend(trigger_notes)
    rec, token_notes = _remove_token_positions(base, rec, min_position_pct)
    chase_notes.extend(token_notes)

    deltas = {a: rec[a] - base[a] for a in ASSETS}
    one_way_turnover = sum(abs(v) for v in deltas.values()) / 2.0
    if one_way_turnover > max_turnover_pct and one_way_turnover > 0:
        factor = max_turnover_pct / one_way_turnover
        rec = {a: base[a] + deltas[a] * factor for a in ASSETS}
        one_way_turnover = max_turnover_pct
        chase_notes.append(f"Scaled all trades to the {max_turnover_pct:.1f}% one-way turnover limit.")

    # Make small mathematical changes non-actionable by freezing them at the current allocation.
    actionable_pct = max(float(min_trade_pct), 100.0 * float(min_trade_dollars) / max(float(portfolio_value), 1.0))
    frozen = rec.copy()
    for a in ASSETS:
        if a == "T-bills / cash equivalents":
            continue
        if abs(frozen[a] - base[a]) < actionable_pct:
            frozen[a] = base[a]
    frozen["T-bills / cash equivalents"] += 100.0 - sum(frozen.values())
    rec = frozen

    deltas = {a: rec[a] - base[a] for a in ASSETS}
    one_way_turnover = sum(abs(v) for v in deltas.values()) / 2.0
    dominant = max(regime_scores.items(), key=lambda kv: kv[1])[0]
    rows = []
    for a in ASSETS:
        delta = rec[a] - base[a]
        trade_dollars = portfolio_value * delta / 100.0
        if delta >= actionable_pct and abs(trade_dollars) >= min_trade_dollars:
            action = "BUY"
        elif delta <= -actionable_pct and abs(trade_dollars) >= min_trade_dollars:
            action = "REDUCE"
        else:
            action = "HOLD"
        why = _asset_rationale(a, action, regime_scores, score_details, market_summary, delta, actionable_pct)
        rows.append({
            "Asset": a,
            "Current %": round(base[a], 1),
            "Recommended %": round(rec[a], 1),
            "Change %": round(delta, 1),
            "Current $": round(portfolio_value * base[a] / 100, 0),
            "Recommended $": round(portfolio_value * rec[a] / 100, 0),
            "Trade $": round(trade_dollars, 0),
            "Action": action,
            "Why": why,
            "Reversal trigger": REVERSAL_TRIGGERS[a],
        })
    df = pd.DataFrame(rows)
    meta = {
        "overlay_strength": overlay,
        "regime_mix_not_probability": weights,
        "one_way_turnover_pct": one_way_turnover,
        "confidence_scale": confidence_scale,
        "chase_notes": chase_notes,
        "dominant_regime": dominant,
        "actionable_threshold_pct": actionable_pct,
        "minimum_position_pct": min_position_pct,
        "minimum_trade_dollars": min_trade_dollars,
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
        rows.append({"Scenario": scenario, "Illustrative portfolio return %": round(ret, 1), "Illustrative P/L $": round(portfolio_value * ret / 100.0, 0)})
    return pd.DataFrame(rows)


def scenario_hedge_alignment(allocation: dict[str, float], portfolio_value: float = 100000.0) -> pd.DataFrame:
    """Translate illustrative scenario stress results into an easier-to-read hedge alignment view.

    This replaces misleading labels such as '90% defensive'. Assets hedge different regimes in
    different directions, especially during a dollar-funding squeeze.
    """
    stress = scenario_stress_test(allocation, portfolio_value)
    if stress.empty:
        return stress
    rows=[]
    for _,r in stress.iterrows():
        ret=float(r["Illustrative portfolio return %"])
        if ret >= 5:
            alignment="STRONG"
        elif ret >= 1:
            alignment="POSITIVE"
        elif ret > -3:
            alignment="MIXED / LIMITED"
        elif ret > -8:
            alignment="VULNERABLE"
        else:
            alignment="HIGHLY VULNERABLE"
        # 50 = approximately neutral; capped for readability, not a probability.
        score=max(0.0,min(100.0,50.0+4.0*ret))
        extra={}
        if r["Scenario"]=="Dollar funding squeeze":
            total=sum(float(allocation.get(a,0)) for a in ASSETS) or 100.0
            cats={}
            for a in ASSETS:
                cls=FUNDING_HEDGE_CLASS[a]; cats[cls]=cats.get(cls,0.0)+100.0*float(allocation.get(a,0))/total
            extra={
                "Direct hedge %":round(cats.get("DIRECT HEDGE",0.0),1),
                "Conditional / unreliable %":round(cats.get("CONDITIONAL / UNRELIABLE",0.0),1),
                "USD-denominated rate-sensitive %":round(cats.get("USD-DENOMINATED / RATE-SENSITIVE",0.0),1),
                "Vulnerable %":round(cats.get("VULNERABLE",0.0),1),
                "Classification note":"USD denomination alone is not a funding-squeeze hedge; T-bills are the clean direct hedge.",
            }
        rows.append({
            "Scenario":r["Scenario"],
            "Hedge alignment":alignment,
            "Alignment index (not probability)":round(score,1),
            "Illustrative return %":ret,
            "Illustrative P/L $":r["Illustrative P/L $"],
            **extra,
        })
    return pd.DataFrame(rows)
