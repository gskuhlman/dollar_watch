from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


def _v(d: dict, *path, default=None):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


def _points(value, bands):
    """bands is [(threshold, points)] sorted ascending. Uses last threshold met."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0
    pts = 0
    for threshold, p in bands:
        if value >= threshold:
            pts = p
    return pts

DEFAULT_OVERRIDES = {
    # Explicit analyst adjustments. Start neutral; change only after source review.
    # 0 = no additional manual evidence, 50 = clearly material, 100 = acute/systemic.
    "broad_fx_intervention": 0,
    "fed_independence_pressure": 0,
    "treasury_auction_stress": 0,
    "foreign_official_selling": 0,
    "brics_payment_progress": 0,
    "central_bank_gold_rotation": 0,
    "stablecoin_dollar_support": 0,
    "geopolitical_cyber_stress": 0,
    "institutional_credibility_stress": 0,
}


def score(snapshot: dict, news_classification: dict, overrides: dict[str, dict]) -> dict:
    m = snapshot.get("market_summary", {})
    f = snapshot.get("fred_summary", {})
    n = news_classification.get("scores", {})
    ov = {k: float(v.get("value", 0)) for k, v in overrides.items()}

    dxy_1m = _v(m, "DXY", "1m", default=0) or 0
    dxy_3m = _v(m, "DXY", "3m", default=0) or 0
    gold_1m = _v(m, "Gold", "1m", default=0) or 0
    gold_3m = _v(m, "Gold", "3m", default=0) or 0
    tlt_1m = _v(m, "Long Treasuries ETF", "1m", default=0) or 0
    btc_1m = _v(m, "Bitcoin", "1m", default=0) or 0
    eur_3m = _v(m, "EURUSD", "3m", default=0) or 0
    jpy_3m = _v(m, "USDJPY", "3m", default=0) or 0

    y10 = _v(f, "10Y Treasury", "last", default=0) or 0
    y30 = _v(f, "30Y Treasury", "last", default=0) or 0
    y30_3m = _v(f, "30Y Treasury", "3m_change", default=0) or 0
    breakeven = _v(f, "10Y breakeven inflation", "last", default=0) or 0
    breakeven_3m = _v(f, "10Y breakeven inflation", "3m_change", default=0) or 0
    real10 = _v(f, "10Y TIPS real yield", "last", default=0) or 0
    vix = _v(f, "VIX", "last", default=0) or 0
    hy = _v(f, "High-yield spread", "last", default=0) or 0
    foreign_custody_yoy = _v(f, "Foreign custody UST YoY change (millions)", "last", default=0) or 0
    foreign_custody_wow = _v(f, "Foreign custody UST WoW change (millions)", "last", default=0) or 0
    foreign_official_3m = _v(f, "Foreign official Treasury holdings (millions)", "3m_change", default=0) or 0
    auction_auto = float(snapshot.get("auction_stress_auto", 0) or 0)

    drivers = {"managed_devaluation": [], "fiscal_inflation": [], "dollar_squeeze": [], "reserve_confidence": []}

    # Managed devaluation: falling dollar + policy intent/intervention + foreign FX appreciation.
    md = 18
    if dxy_3m < -0.03:
        md += 12; drivers["managed_devaluation"].append("DXY down >3% over ~3 months")
    if dxy_3m < -0.07:
        md += 10; drivers["managed_devaluation"].append("DXY down >7% over ~3 months")
    if eur_3m > 0.03:
        md += 5; drivers["managed_devaluation"].append("EUR strengthening vs USD")
    if jpy_3m < -0.03:
        md += 5; drivers["managed_devaluation"].append("JPY strengthening vs USD")
    md += 0.18 * ov.get("broad_fx_intervention", 0)
    md += 0.12 * ov.get("fed_independence_pressure", 0)
    md += max(-5, min(12, 2.0 * n.get("policy_devaluation", 0)))
    md -= 0.10 * ov.get("stablecoin_dollar_support", 0)
    managed = _clamp(md)

    # Fiscal/inflation: high/rising long yields, breakevens, gold, auction/credibility stress.
    fi = 18
    fi += _points(y30, [(4.5, 6), (5.0, 12), (5.5, 20), (6.0, 28)])
    if y30_3m > 0.25:
        fi += 8; drivers["fiscal_inflation"].append("30Y yield up >25bp over ~3 months")
    if y30_3m > 0.60:
        fi += 8; drivers["fiscal_inflation"].append("30Y yield up >60bp over ~3 months")
    if breakeven > 2.5:
        fi += 5; drivers["fiscal_inflation"].append("10Y inflation breakeven >2.5%")
    if breakeven_3m > 0.20:
        fi += 6; drivers["fiscal_inflation"].append("Inflation expectations rising")
    if gold_3m > 0.08:
        fi += 7; drivers["fiscal_inflation"].append("Gold up >8% over ~3 months")
    fi += 0.18 * auction_auto
    if auction_auto >= 40:
        drivers["fiscal_inflation"].append(f"Treasury auction absorption stress {auction_auto:.0f}/100")
    fi += 0.10 * ov.get("treasury_auction_stress", 0)
    fi += 0.10 * ov.get("institutional_credibility_stress", 0)
    fiscal = _clamp(fi)

    # Dollar squeeze: dollar strengthens while risk/funding stress rises.
    ds = 10
    if dxy_1m > 0.03:
        ds += 12; drivers["dollar_squeeze"].append("DXY up >3% in ~1 month")
    if dxy_1m > 0.06:
        ds += 10; drivers["dollar_squeeze"].append("DXY up >6% in ~1 month")
    ds += _points(vix, [(20, 8), (30, 16), (40, 25)])
    ds += _points(hy, [(4, 6), (5, 12), (7, 20)])
    ds += max(0, min(16, 2.0 * n.get("funding_stress", 0)))
    if tlt_1m < -0.05:
        ds += 5; drivers["dollar_squeeze"].append("Long bonds under pressure")
    squeeze = _clamp(ds)

    # Reserve-confidence: toxic combination: USD down + long yields up + gold up + external selling.
    rc = 8
    toxic = (dxy_3m < -0.03) + (y30_3m > 0.25) + (gold_3m > 0.08)
    if toxic >= 2:
        rc += 15; drivers["reserve_confidence"].append("Two legs of USD-down / long-yields-up / gold-up are active")
    if toxic == 3:
        rc += 18; drivers["reserve_confidence"].append("Toxic trio active: USD down + long yields up + gold up")
    if foreign_custody_yoy < -100000:
        rc += 7; drivers["reserve_confidence"].append("Foreign-custody Treasury holdings down >$100B YoY")
    if foreign_custody_yoy < -250000:
        rc += 7; drivers["reserve_confidence"].append("Foreign-custody Treasury holdings down >$250B YoY")
    if foreign_official_3m < -100000:
        rc += 6; drivers["reserve_confidence"].append("Foreign official Treasury holdings fell >$100B over ~3 months")
    rc += 0.10 * ov.get("foreign_official_selling", 0)
    rc += 0.10 * ov.get("brics_payment_progress", 0)
    rc += 0.10 * ov.get("central_bank_gold_rotation", 0)
    rc += 0.08 * ov.get("institutional_credibility_stress", 0)
    rc += max(-4, min(14, 1.7 * n.get("external_dedollarization", 0)))
    rc -= 0.08 * ov.get("stablecoin_dollar_support", 0)
    reserve = _clamp(rc)

    # Supporting component scores for interpretation.
    foreign_auto = 0
    if foreign_custody_yoy < -100000: foreign_auto += 12
    if foreign_custody_yoy < -250000: foreign_auto += 10
    if foreign_official_3m < -100000: foreign_auto += 8
    external = _clamp(15 + foreign_auto + 0.20*ov.get("brics_payment_progress",0) + 0.12*ov.get("foreign_official_selling",0) + 0.15*ov.get("central_bank_gold_rotation",0) + max(-5, min(20, 2*n.get("external_dedollarization",0))))
    support = _clamp(20 + 0.45*ov.get("stablecoin_dollar_support",0) + max(-5, min(15, 2*n.get("dollar_support",0))))
    plumbing = _clamp(8 + 0.55*auction_auto + 0.20*ov.get("treasury_auction_stress",0) + _points(vix, [(25,10),(35,20)]) + max(0,min(20,2*n.get("funding_stress",0))))

    return {
        "regimes": {
            "Managed dollar devaluation": round(managed, 1),
            "Fiscal / inflation crisis": round(fiscal, 1),
            "Dollar funding squeeze": round(squeeze, 1),
            "Reserve-confidence crisis": round(reserve, 1),
        },
        "components": {
            "External de-dollarization pressure": round(external, 1),
            "Structural dollar support": round(support, 1),
            "Treasury / funding plumbing stress": round(plumbing, 1),
        },
        "drivers": drivers,
        "diagnostics": {
            "dxy_1m": dxy_1m, "dxy_3m": dxy_3m, "gold_3m": gold_3m,
            "y30": y30, "y30_3m": y30_3m, "breakeven": breakeven,
            "real10": real10, "vix": vix, "hy_spread": hy,
            "foreign_custody_yoy_millions": foreign_custody_yoy, "foreign_custody_wow_millions": foreign_custody_wow,
            "foreign_official_3m_change_millions": foreign_official_3m, "auction_stress_auto": auction_auto,
        },
    }
