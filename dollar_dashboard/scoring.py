from __future__ import annotations

import math
from typing import Any


def _v(d: dict, *path, default=None):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _safe(x, default=0.0):
    try:
        x = float(x)
        return default if math.isnan(x) else x
    except Exception:
        return default


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


def _points(value, bands):
    value = _safe(value, None)
    if value is None:
        return 0
    pts = 0
    for threshold, p in bands:
        if value >= threshold:
            pts = p
    return pts


DEFAULT_OVERRIDES = {
    # 0 = absent/benign; 50 = clearly material; 100 = acute/systemic.
    "broad_fx_intervention": 0,
    "fed_independence_pressure": 0,
    "treasury_auction_stress": 0,
    "foreign_official_selling": 0,
    "brics_payment_progress": 0,
    "central_bank_gold_rotation": 0,
    "stablecoin_dollar_support": 0,
    "commodity_dedollarization": 0,
    "geopolitical_cyber_stress": 0,
    "institutional_credibility_stress": 0,
    "capital_control_or_holder_fee_risk": 0,
}


def score(snapshot: dict, news_classification: dict, overrides: dict[str, dict]) -> dict:
    m = snapshot.get("market_summary", {})
    f = snapshot.get("fred_summary", {})
    n = news_classification.get("scores", {})
    ov = {k: float(v.get("value", 0)) for k, v in overrides.items()}

    dxy_1m = _safe(_v(m, "DXY", "1m"))
    dxy_3m = _safe(_v(m, "DXY", "3m"))
    dxy_1y = _safe(_v(m, "DXY", "1y"))
    gold_3m = _safe(_v(m, "Gold", "3m"))
    tlt_1m = _safe(_v(m, "Long Treasuries ETF", "1m"))
    eur_3m = _safe(_v(m, "EURUSD", "3m"))
    jpy_3m = _safe(_v(m, "USDJPY", "3m"))
    chf_3m = _safe(_v(m, "USDCHF", "3m"))

    y30 = _safe(_v(f, "30Y Treasury", "last"))
    y30_3m = _safe(_v(f, "30Y Treasury", "3m_change"))
    breakeven = _safe(_v(f, "10Y breakeven inflation", "last"))
    breakeven_3m = _safe(_v(f, "10Y breakeven inflation", "3m_change"))
    term_premium = _safe(_v(f, "10Y term premium", "last"))
    term_premium_3m = _safe(_v(f, "10Y term premium", "3m_change"))
    vix = _safe(_v(f, "VIX", "last"))
    hy = _safe(_v(f, "High-yield spread", "last"))
    nfci = _safe(_v(f, "Financial Conditions Index", "last"))
    swaps = _safe(_v(f, "Central bank liquidity swaps (millions)", "last"))
    swaps_1m = _safe(_v(f, "Central bank liquidity swaps (millions)", "1m_change"))
    foreign_custody_yoy = _safe(_v(f, "Foreign custody UST YoY change (millions)", "last"))
    foreign_official_3m = _safe(_v(f, "Foreign official Treasury holdings (millions)", "3m_change"))

    auction_auto = _safe(snapshot.get("auction_stress_auto"))
    cftc_pressure = _safe(snapshot.get("cftc_usd_downside_pressure"))
    tic_pressure = _safe(snapshot.get("tic_dedollarization_pressure"))
    stablecoin_auto = _safe(snapshot.get("stablecoin_dollar_support_auto"))
    data_confidence = _safe(snapshot.get("data_confidence"), 50.0)

    drivers = {"managed_devaluation": [], "fiscal_inflation": [], "dollar_squeeze": [], "reserve_confidence": []}

    # ----- Leading/transmission components -----
    policy_intent = 12.0
    policy_intent += 0.36 * ov.get("broad_fx_intervention", 0)
    policy_intent += 0.23 * ov.get("fed_independence_pressure", 0)
    policy_intent += 0.16 * ov.get("capital_control_or_holder_fee_risk", 0)
    policy_intent += max(-12, min(20, 2.0 * n.get("policy_devaluation", 0)))
    policy_intent = _clamp(policy_intent)

    positioning = _clamp(cftc_pressure if cftc_pressure else 25.0)

    external = 0.55 * (tic_pressure if tic_pressure else 15.0)
    external += 0.15 * ov.get("foreign_official_selling", 0)
    external += 0.20 * ov.get("brics_payment_progress", 0)
    external += 0.13 * ov.get("central_bank_gold_rotation", 0)
    external += 0.16 * ov.get("commodity_dedollarization", 0)
    external += max(-8, min(20, 2.0 * n.get("external_dedollarization", 0)))
    if foreign_custody_yoy < -100000:
        external += 8
    if foreign_official_3m < -100000:
        external += 7
    external = _clamp(external)

    support = 0.65 * (stablecoin_auto if stablecoin_auto else 20.0)
    support += 0.25 * ov.get("stablecoin_dollar_support", 0)
    support += max(-8, min(18, 2.0 * n.get("dollar_support", 0)))
    support = _clamp(support)

    fiscal_term = 15.0
    fiscal_term += _points(y30, [(4.5, 5), (5.0, 12), (5.5, 20), (6.0, 30)])
    if y30_3m > 0.25:
        fiscal_term += 8
    if y30_3m > 0.60:
        fiscal_term += 8
    if term_premium > 0.65:
        fiscal_term += 8
    if term_premium > 1.00:
        fiscal_term += 10
    if term_premium_3m > 0.20:
        fiscal_term += 7
    fiscal_term += 0.22 * auction_auto
    fiscal_term += 0.10 * ov.get("treasury_auction_stress", 0)
    fiscal_term += 0.12 * ov.get("institutional_credibility_stress", 0)
    fiscal_term = _clamp(fiscal_term)

    plumbing = 8.0
    plumbing += _points(vix, [(20, 8), (30, 18), (40, 30)])
    plumbing += _points(hy, [(4, 6), (5, 14), (7, 25)])
    plumbing += _points(nfci, [(0.0, 5), (0.5, 12), (1.0, 20)])
    if swaps > 5000 or swaps_1m > 2500:
        plumbing += 12
    plumbing += 0.30 * auction_auto
    plumbing += 0.12 * ov.get("geopolitical_cyber_stress", 0)
    plumbing += max(0, min(20, 2.0 * n.get("funding_stress", 0)))
    plumbing = _clamp(plumbing)

    institutional = _clamp(
        8 + 0.38 * ov.get("institutional_credibility_stress", 0)
        + 0.24 * ov.get("fed_independence_pressure", 0)
        + 0.25 * ov.get("capital_control_or_holder_fee_risk", 0)
        + max(0, min(18, 2.0 * n.get("institutional_stress", 0)))
    )

    # ----- Market confirmation -----
    confirmation = 8.0
    toxic_legs = 0
    if dxy_3m < -0.03:
        confirmation += 12; toxic_legs += 1
    if dxy_3m < -0.07:
        confirmation += 8
    if y30_3m > 0.25:
        confirmation += 12; toxic_legs += 1
    if gold_3m > 0.08:
        confirmation += 12; toxic_legs += 1
    if toxic_legs >= 2:
        confirmation += 8
    if toxic_legs == 3:
        confirmation += 10
    if eur_3m > 0.03:
        confirmation += 4
    if jpy_3m < -0.03:
        confirmation += 4
    if chf_3m < -0.03:
        confirmation += 4
    confirmation = _clamp(confirmation)

    early_warning = _clamp(
        0.22 * policy_intent + 0.18 * positioning + 0.20 * external
        + 0.18 * fiscal_term + 0.12 * plumbing + 0.10 * institutional
        - 0.10 * max(0, support - 50)
    )

    # ----- Four regime scores -----
    managed = 12.0 + 0.44 * policy_intent + 0.18 * positioning + 0.26 * confirmation - 0.10 * support
    if dxy_3m < -0.03:
        drivers["managed_devaluation"].append("DXY down >3% over ~3 months")
    if cftc_pressure >= 65:
        drivers["managed_devaluation"].append("CFTC FX positioning is tilted toward USD downside")
    if policy_intent >= 55:
        drivers["managed_devaluation"].append("Policy-intent indicators are elevated")
    managed = _clamp(managed)

    fiscal = 10.0 + 0.58 * fiscal_term + 0.15 * institutional + 0.18 * confirmation
    if breakeven > 2.5:
        fiscal += 5; drivers["fiscal_inflation"].append("10Y breakeven inflation >2.5%")
    if breakeven_3m > 0.20:
        fiscal += 5; drivers["fiscal_inflation"].append("Inflation expectations rising")
    if term_premium > 0.65:
        drivers["fiscal_inflation"].append("10Y term premium is elevated")
    if auction_auto >= 40:
        drivers["fiscal_inflation"].append(f"Treasury auction absorption stress {auction_auto:.0f}/100")
    fiscal = _clamp(fiscal)

    squeeze = 8.0 + 0.64 * plumbing
    if dxy_1m > 0.03:
        squeeze += 12; drivers["dollar_squeeze"].append("DXY up >3% in ~1 month")
    if dxy_1m > 0.06:
        squeeze += 8
    if swaps > 5000 or swaps_1m > 2500:
        drivers["dollar_squeeze"].append("Federal Reserve foreign-currency swap usage is rising/elevated")
    if tlt_1m < -0.05:
        squeeze += 4; drivers["dollar_squeeze"].append("Long Treasuries under pressure during funding stress")
    squeeze = _clamp(squeeze)

    reserve = 5.0 + 0.30 * external + 0.21 * fiscal_term + 0.17 * institutional + 0.30 * confirmation - 0.10 * support
    if toxic_legs >= 2:
        drivers["reserve_confidence"].append("Multiple legs of USD-down / long-yields-up / gold-up are active")
    if toxic_legs == 3:
        drivers["reserve_confidence"].append("Toxic trio active: USD down + long yields up + gold up")
    if tic_pressure >= 50:
        drivers["reserve_confidence"].append("Country-level TIC holdings show material de-dollarization pressure")
    if foreign_custody_yoy < -100000:
        drivers["reserve_confidence"].append("Foreign-custody Treasuries down >$100B YoY")
    reserve = _clamp(reserve)

    if early_warning >= 55 and confirmation < 40:
        phase = "PRECONDITION / EARLY WARNING"
    elif early_warning >= 50 and confirmation >= 40:
        phase = "TRANSITION"
    elif confirmation >= 60 and max(managed, fiscal, reserve, squeeze) >= 70:
        phase = "CONFIRMED STRESS"
    elif max(managed, fiscal, reserve, squeeze) >= 50:
        phase = "WATCH / MIXED"
    else:
        phase = "QUIET / NORMAL"

    return {
        "regimes": {
            "Managed dollar devaluation": round(managed, 1),
            "Fiscal / inflation crisis": round(fiscal, 1),
            "Dollar funding squeeze": round(squeeze, 1),
            "Reserve-confidence crisis": round(reserve, 1),
        },
        "components": {
            "Policy intent / intervention": round(policy_intent, 1),
            "FX positioning pressure": round(positioning, 1),
            "External de-dollarization pressure": round(external, 1),
            "Structural dollar support": round(support, 1),
            "Fiscal / term-premium pressure": round(fiscal_term, 1),
            "Treasury / funding plumbing stress": round(plumbing, 1),
            "Institutional credibility stress": round(institutional, 1),
            "Market confirmation": round(confirmation, 1),
        },
        "early_warning_index": round(early_warning, 1),
        "confirmation_index": round(confirmation, 1),
        "phase": phase,
        "confidence": round(data_confidence, 1),
        "drivers": drivers,
        "diagnostics": {
            "dxy_1m": dxy_1m, "dxy_3m": dxy_3m, "dxy_1y": dxy_1y, "gold_3m": gold_3m,
            "y30": y30, "y30_3m": y30_3m, "breakeven": breakeven,
            "term_premium": term_premium, "term_premium_3m": term_premium_3m,
            "vix": vix, "hy_spread": hy, "nfci": nfci, "central_bank_swaps": swaps,
            "foreign_custody_yoy_millions": foreign_custody_yoy,
            "foreign_official_3m_change_millions": foreign_official_3m,
            "auction_stress_auto": auction_auto, "cftc_usd_downside_pressure": cftc_pressure,
            "tic_dedollarization_pressure": tic_pressure, "stablecoin_dollar_support_auto": stablecoin_auto,
        },
    }
